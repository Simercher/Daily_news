from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from news_system.processors.event_clusterer import cluster_events
from news_system.processors.scorer import score_event
from news_system.storage.repositories import ArticleRepository

from .shared import _persist_events


def daily_event_job(db: Session | None = None, lookback_hours: int = 24, limit: int = 10, *, articles: Iterable | None = None):
    if articles is None and db:
        articles = ArticleRepository(db).list_recent(hours=lookback_hours, include_duplicates=False)
    events = [score_event(e) for e in cluster_events(list(articles or []))]
    events = sorted(events, key=lambda e: e.final_score, reverse=True)[:limit]
    return _persist_events(db, events) if db else events
