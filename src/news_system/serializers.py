from __future__ import annotations

from datetime import date, datetime

from news_system.db.models import EventModel


def _iso(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def event_to_dict(event: EventModel) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "normalized_title": event.normalized_title,
        "event_date": _iso(event.event_date),
        "first_seen_at": _iso(event.first_seen_at),
        "last_seen_at": _iso(event.last_seen_at),
        "article_count": event.article_count,
        "source_count": event.source_count,
        "popular_score": event.popular_score,
        "importance_score": event.importance_score,
        "breaking_score": event.breaking_score,
        "final_score": event.final_score,
        "is_breaking": event.is_breaking,
        "keywords": event.keywords or [],
        "entities": event.entities or {},
    }


def events_payload(events: list[EventModel], **extra) -> dict:
    return {**extra, "count": len(events), "events": [event_to_dict(e) for e in events]}
