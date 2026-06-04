from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from news_system.db.models import ArticleModel, EventModel
from news_system.processors.event_fingerprint import generate_fingerprint
from news_system.processors.normalizer import normalize_title
from news_system.processors.representative_articles import select_representative
from news_system.storage.repositories import EventRepository


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


def _source_key(article) -> str | None:
    return getattr(article, "source_name", None) or getattr(article, "source_domain", None) or getattr(article, "external_id", None)


def _is_trusted_source(article) -> bool:
    raw = getattr(article, "raw_payload", None) or {}
    cfg = raw.get("source_config") if isinstance(raw, dict) else None
    if isinstance(cfg, dict):
        cred = cfg.get("credibility_score")
        if cred is not None:
            return float(cred) >= 0.75
        if cfg.get("trusted") is not None:
            return bool(cfg.get("trusted"))
    return True


def _event_category(articles) -> str | None:
    counts = Counter(getattr(a, "category", None) for a in articles if getattr(a, "category", None))
    if counts:
        return counts.most_common(1)[0][0]
    text = " ".join(
        " ".join([
            getattr(a, "title", "") or "",
            getattr(a, "description", "") or "",
            " ".join(getattr(a, "keywords", []) or []),
        ]).lower()
        for a in articles
    )
    if any(term in text for term in ("earthquake", "quake", "flood", "hurricane", "wildfire", "disaster")):
        return "disaster"
    if any(term in text for term in ("war", "attack", "missile", "invasion", "conflict")):
        return "war_conflict"
    return None


def _persist_events(db: Session, events) -> list[EventModel]:
    repo = EventRepository(db); out = []
    for ev in events:
        event_dt = max((a.published_at for a in ev.articles), default=datetime.now(timezone.utc))
        sources = {_source_key(a) for a in ev.articles if _source_key(a)}
        trusted_sources = {_source_key(a) for a in ev.articles if _source_key(a) and _is_trusted_source(a)}
        category = getattr(ev, "category", None) or _event_category(ev.articles)
        breaking_detected_at = datetime.now(timezone.utc) if getattr(ev, "is_breaking", False) else None

        entities_list = list(getattr(ev, "entities", set()) or [])
        keywords_list = list(getattr(ev, "keywords", set()) or [])
        first_article = ev.articles[0] if ev.articles else None
        collected_at = getattr(first_article, "collected_at", None) if first_article else None
        source_country = getattr(first_article, "country", None) if first_article else None
        normalized_title = getattr(ev, "normalized_title", None) or normalize_title(ev.title)
        fingerprint = generate_fingerprint(
            category=category,
            dt=event_dt,
            collected_at=collected_at,
            entities=entities_list,
            keywords=keywords_list,
            source_country=source_country,
            normalized_title=normalized_title,
        )

        best_article_id, representative_list = select_representative(ev.articles)

        credibility_trusted = {
            _source_key(a) for a in ev.articles
            if _source_key(a) and _is_trusted_source(a)
        }

        score_breakdown = getattr(ev, "score_breakdown", None)
        if score_breakdown is None:
            score_breakdown = {}

        model = EventModel(
            title=ev.title,
            normalized_title=getattr(ev, "normalized_title", None) or normalize_title(ev.title),
            event_date=event_dt.date(),
            first_seen_at=min((a.published_at for a in ev.articles), default=event_dt),
            last_seen_at=event_dt,
            keywords=list(ev.keywords),
            entities=ev.entities if isinstance(getattr(ev, "entities", {}), dict) else {"items": list(ev.entities)},
            category=category,
            article_count=len(ev.articles),
            source_count=len(sources),
            trusted_source_count=len(credibility_trusted),
            country_count=len({getattr(a, "country", None) for a in ev.articles if getattr(a, "country", None)}),
            popular_score=ev.source_diversity_score,
            importance_score=ev.severity_score,
            breaking_score=getattr(ev, "breaking_score", ev.velocity_score),
            final_score=ev.final_score,
            status="active",
            is_breaking=getattr(ev, "is_breaking", False),
            breaking_detected_at=breaking_detected_at,
            event_fingerprint=fingerprint,
            score_breakdown=score_breakdown,
            representative_article_id=best_article_id,
            last_scored_at=getattr(ev, "last_scored_at", None),
            cluster_method="fingerprint+title+keyword",
        )
        persisted = repo.upsert_by_day_title(model, ev.articles)

        if persisted:
            persisted.event_fingerprint = fingerprint
            persisted.score_breakdown = score_breakdown
            persisted.representative_article_id = best_article_id
            persisted.last_scored_at = getattr(ev, "last_scored_at", None)
            persisted.cluster_method = "fingerprint+title+keyword"

        out.append(persisted)
    db.commit(); return out
