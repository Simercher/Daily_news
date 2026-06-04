from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from news_system.processors.breaking_detector import is_breaking
from news_system.processors.event_clusterer import cluster_events
from news_system.processors.scorer import _severity_keyword_score, score_event
from news_system.storage.repositories import ArticleRepository

from .shared import _event_category, _is_trusted_source, _persist_events, _source_key

BREAKING_CATEGORIES = {"war_conflict", "disaster", "politics", "economy", "health"}
EXTREME_BREAKING_CATEGORIES = {"war_conflict", "disaster"}


def _breaking_score(ev, trusted_source_count: int, recent_article_count: int, severity_keyword_score: float) -> float:
    source_component = min(1.0, trusted_source_count / 2.0)
    article_component = min(1.0, recent_article_count / 3.0)
    return round(max(getattr(ev, "final_score", 0.0), 0.4 * severity_keyword_score + 0.3 * source_component + 0.3 * article_component), 4)


def _apply_breaking_rules(ev, *, category: str | None, trusted_source_count: int, recent_article_count: int, severity_keyword_score: float, breaking_score: float) -> bool:
    normal = (
        breaking_score >= 0.75
        and trusted_source_count >= 2
        and recent_article_count >= 3
        and category in BREAKING_CATEGORIES
    )
    relaxed = (
        category in EXTREME_BREAKING_CATEGORIES
        and trusted_source_count >= 1
        and recent_article_count >= 2
        and severity_keyword_score >= 0.4
    )
    return normal or relaxed


def breaking_watch_job(db: Session | None = None, since_minutes: int = 60, limit: int = 20, *, articles: Iterable | None = None):
    if articles is None and db:
        hours = max(1, (since_minutes + 59) // 60)
        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        articles = [a for a in ArticleRepository(db).list_recent(hours=hours, include_duplicates=False) if a.published_at >= since]
    events = []
    for ev in [score_event(e) for e in cluster_events(list(articles or []))]:
        category = _event_category(ev.articles)
        trusted_count = len({
            _source_key(a) for a in ev.articles
            if _source_key(a) and _is_trusted_source(a)
        })
        recent_count = len(ev.articles)
        severity = getattr(ev, "severity_score", 0.0)
        sev_kw_score = _severity_keyword_score(ev.articles)
        ev.category = category
        ev.breaking_score = _breaking_score(ev, trusted_count, recent_count, sev_kw_score)
        ev.is_breaking = _apply_breaking_rules(
            ev,
            category=category,
            trusted_source_count=trusted_count,
            recent_article_count=recent_count,
            severity_keyword_score=sev_kw_score,
            breaking_score=ev.breaking_score,
        )
        if ev.is_breaking: events.append(ev)
    events = sorted(events, key=lambda e: (getattr(e, "breaking_score", 0.0), getattr(e, "final_score", 0.0)), reverse=True)[:limit]
    return _persist_events(db, events) if db else events
