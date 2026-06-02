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
    return ArticleModel(**{k: v for k, v in data.items() if hasattr(ArticleModel, k)})


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
        run = CollectionRunRepository(db).start(name) if db else None
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
        model = EventModel(title=ev.title, event_date=max((a.published_at for a in ev.articles), default=datetime.now(timezone.utc)), keywords=list(ev.keywords), entities=list(ev.entities), article_count=len(ev.articles), velocity_score=ev.velocity_score, source_diversity_score=ev.source_diversity_score, severity_score=ev.severity_score, final_score=ev.final_score, is_breaking=getattr(ev, "is_breaking", False))
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
