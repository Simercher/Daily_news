from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import yaml
from sqlalchemy.orm import Session

from news_system.collectors import GDELTCollector, NewsAPICollector, RSSCollector
from news_system.db.models import ArticleModel, EventModel
from news_system.processors.deduplicator import mark_duplicates
from news_system.processors.event_clusterer import cluster_events
from news_system.processors.scorer import score_event
from news_system.processors.breaking_detector import is_breaking
from news_system.storage.repositories import ArticleRepository, CollectionRunRepository, EventRepository, SourceRepository


def _to_model(a) -> ArticleModel:
    if isinstance(a, ArticleModel): return a
    data = a.model_dump() if hasattr(a, "model_dump") else dict(a)
    aliases = {
        "source_id": "external_id",
        "content": "content_snippet",
        "raw": "raw_payload",
        "duplicate_of_id": "duplicate_of_article_id",
    }
    for old, new in aliases.items():
        if old in data and new not in data:
            data[new] = data.pop(old)
    raw_payload = dict(data.get("raw_payload") or {})
    for compat_key in ("keywords", "entities"):
        if compat_key in data:
            raw_payload[compat_key] = data.pop(compat_key)
    data["raw_payload"] = raw_payload
    return ArticleModel(**{k: v for k, v in data.items() if k in ArticleModel.__table__.columns})


def _load_collectors(config_path: str | Path = "config/sources.yaml"):
    path = Path(config_path)
    if not path.exists(): return []
    data = yaml.safe_load(path.read_text()) or {}
    collectors = []
    for src in data.get("sources", data if isinstance(data, list) else []):
        if not src.get("enabled", True): continue
        typ = (src.get("type") or "rss").lower()
        if typ == "rss": collectors.append(RSSCollector(src["url"], source_name=src.get("name")))
        elif typ == "newsapi": collectors.append(NewsAPICollector(src.get("api_key", ""), endpoint=src.get("endpoint", "top-headlines")))
        elif typ == "gdelt": collectors.append(GDELTCollector())
    return collectors


def collect_job(db: Session | None = None, source: str = "all", lookback_hours: int = 1, collectors=None, config_path: str | Path = "config/sources.yaml"):
    collectors = collectors if collectors is not None else _load_collectors(config_path)
    raw_articles = []
    runs = []
    for c in collectors:
        name = getattr(c, "source_name", None) or c.__class__.__name__
        run = CollectionRunRepository(db).start(name, source_type=c.__class__.__name__.replace("Collector", "").lower() or "rss", lookback_hours=lookback_hours) if db else None
        fetched = inserted = 0; error = None
        try:
            items = c.fetch(lookback_hours=lookback_hours) or []
            fetched = len(items); raw_articles.extend(items)
        except Exception as exc:  # test-friendly: record and continue
            error = str(exc)
        if db and run:
            CollectionRunRepository(db).finish(run, fetched_count=fetched, inserted_count=inserted, error=error); runs.append(run)
    marked = mark_duplicates([_to_model(a) for a in raw_articles])
    if not db: return marked
    repo = ArticleRepository(db); inserted = 0
    for article in marked:
        _, was_inserted = repo.upsert(article); inserted += int(was_inserted)
    for run in runs:
        run.inserted_count = inserted
    db.commit()
    return {"fetched": len(raw_articles), "inserted": inserted, "articles": marked, "runs": runs}


def _persist_events(db: Session, events) -> list[EventModel]:
    repo = EventRepository(db); out = []
    for ev in events:
        event_dt = max((a.published_at for a in ev.articles), default=datetime.now(timezone.utc))
        model = EventModel(
            title=ev.title,
            normalized_title=getattr(ev, "normalized_title", None),
            event_date=event_dt.date(),
            first_seen_at=min((a.published_at for a in ev.articles), default=event_dt),
            last_seen_at=event_dt,
            keywords=list(ev.keywords),
            entities=ev.entities if isinstance(getattr(ev, "entities", {}), dict) else {"items": list(ev.entities)},
            article_count=len(ev.articles),
            source_count=len({getattr(a, "source_name", None) or getattr(a, "source_domain", None) for a in ev.articles if getattr(a, "source_name", None) or getattr(a, "source_domain", None)}),
            popular_score=ev.source_diversity_score,
            importance_score=ev.severity_score,
            breaking_score=ev.velocity_score,
            final_score=ev.final_score,
            is_breaking=getattr(ev, "is_breaking", False),
            breaking_detected_at=datetime.now(timezone.utc) if getattr(ev, "is_breaking", False) else None,
        )
        repo.add(model, ev.articles); out.append(model)
    db.commit(); return out


def daily_event_job(db: Session | None = None, articles: Iterable | None = None, lookback_hours: int = 24, limit: int = 20):
    if articles is None and db:
        articles = ArticleRepository(db).list_recent(hours=lookback_hours, include_duplicates=False)
    events = [score_event(e) for e in cluster_events(list(articles or []))]
    events = sorted(events, key=lambda e: e.final_score, reverse=True)[:limit]
    return _persist_events(db, events) if db else events


def breaking_watch_job(db: Session | None = None, articles: Iterable | None = None, since_minutes: int = 60):
    if articles is None and db:
        articles = ArticleRepository(db).list_recent(hours=max(1, since_minutes // 60), include_duplicates=False)
    events = []
    for ev in [score_event(e) for e in cluster_events(list(articles or []))]:
        ev.is_breaking = is_breaking(ev)
        if ev.is_breaking: events.append(ev)
    return _persist_events(db, events) if db else events
