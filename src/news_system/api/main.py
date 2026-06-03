from __future__ import annotations

from datetime import datetime, timezone, timedelta, date as date_type

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from news_system.db.models import ArticleModel, EventArticle, EventModel
from news_system.db.session import get_session_local
from news_system.serializers import event_to_dict, events_payload
from news_system.storage.repositories import EventRepository

app = FastAPI(title="Daily_news")


def get_db():
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()


@app.get("/events/daily")
def daily(date: str, limit: int = 10, db: Session = Depends(get_db)):
    event_day = date_type.fromisoformat(date)
    events = EventRepository(db).list_daily(event_day, limit=limit)
    return events_payload(events, date=date, limit=limit)


@app.get("/events/breaking")
def breaking(since_minutes: int = 180, limit: int = 20, db: Session = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    events = db.query(EventModel).filter(EventModel.is_breaking == True, EventModel.created_at >= since).order_by(EventModel.final_score.desc()).limit(limit).all()
    return events_payload(events, since_minutes=since_minutes, limit=limit)


@app.get("/events/{event_id}")
def event_detail(event_id: int, db: Session = Depends(get_db)):
    ev = db.get(EventModel, event_id)
    links = db.query(EventArticle).filter_by(event_id=event_id).all()
    articles = [db.get(ArticleModel, l.article_id) for l in links]
    return {
        "event": event_to_dict(ev) if ev else None,
        "articles": [
            {
                "id": a.id,
                "title": a.title,
                "url": a.url,
                "source_name": a.source_name,
                "published_at": a.published_at.isoformat() if a.published_at else None,
            }
            for a in articles if a is not None
        ],
    }
