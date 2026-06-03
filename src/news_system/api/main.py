from __future__ import annotations

from datetime import date as date_type

from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from news_system.db.models import ArticleModel, EventArticle, EventModel, NewsSource
from news_system.db.session import get_session_local
from news_system.processors.scorer import _get_credibility
from news_system.serializers import (
    article_to_dict,
    enrich_event_with_articles,
    event_to_dict,
    events_payload,
    get_trusted_articles,
    select_representative_articles,
)
from news_system.storage.repositories import EventRepository

app = FastAPI(title="Daily_news")


def get_db():
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()


def _load_articles_for_event(db: Session, event_id: int, limit: int | None = None, offset: int = 0) -> list[ArticleModel]:
    """Fetch ArticleModel instances linked to the given event, with pagination.

    Sorted by published_at DESC (fallback collected_at).
    """
    stmt = (
        select(ArticleModel)
        .join(EventArticle, ArticleModel.id == EventArticle.article_id)
        .where(EventArticle.event_id == event_id)
        .order_by(ArticleModel.published_at.desc().nullslast(), ArticleModel.collected_at.desc().nullslast())
    )
    if offset > 0:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.execute(stmt).scalars())


@app.get("/events/daily")
def daily(date: str, limit: int = 10, db: Session = Depends(get_db)):
    event_day = date_type.fromisoformat(date)
    events = EventRepository(db).list_daily(event_day, limit=limit)
    articles_by_event: dict[int, list[ArticleModel]] = {}
    for ev in events:
        articles_by_event[ev.id] = _load_articles_for_event(db, ev.id)
    return events_payload(
        events, articles_by_event=articles_by_event, date=date, limit=limit
    )


@app.get("/events/breaking")
def breaking(since_minutes: int = 180, limit: int = 20, db: Session = Depends(get_db)):
    events = EventRepository(db).list_breaking(
        since_minutes=since_minutes, limit=limit
    )
    articles_by_event: dict[int, list[ArticleModel]] = {}
    for ev in events:
        articles_by_event[ev.id] = _load_articles_for_event(db, ev.id)
    return events_payload(
        events,
        articles_by_event=articles_by_event,
        since_minutes=since_minutes,
        limit=limit,
    )


@app.get("/events/{event_id}")
def event_detail(event_id: int, article_limit: int = 50, article_offset: int = 0, db: Session = Depends(get_db)):
    ev = db.get(EventModel, event_id)
    if ev is None:
        return {"event": None}
    all_articles = _load_articles_for_event(db, event_id, limit=article_limit, offset=article_offset)
    # Load full set for representative/trusted selection (no pagination for those)
    all_articles_full = _load_articles_for_event(db, event_id)
    event_dict = event_to_dict(ev)
    event_dict["representative_articles"] = [
        article_to_dict(a) for a in select_representative_articles(all_articles_full)
    ]
    event_dict["trusted_articles"] = [
        article_to_dict(a) for a in get_trusted_articles(all_articles_full)
    ]
    event_dict["all_articles"] = [article_to_dict(a) for a in all_articles]
    return {"event": event_dict}