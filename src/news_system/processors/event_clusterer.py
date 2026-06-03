from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from rapidfuzz import fuzz

from news_system.processors.event_fingerprint import generate_fingerprint, fingerprint_overlap


@dataclass
class Event:
    title: str
    articles: list = field(default_factory=list)
    keywords: set[str] = field(default_factory=set)
    entities: set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    final_score: float = 0.0
    severity_score: float = 0.0
    velocity_score: float = 0.0
    source_diversity_score: float = 0.0
    popular_score: float = 0.0
    importance_score: float = 0.0
    breaking_score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)
    last_scored_at: datetime | None = None
    event_fingerprint: str | None = None
    previous_article_count: int | None = None


def keyword_overlap(a, b):
    sa = set(a or [])
    sb = set(b or [])
    return len(sa & sb) / max(1, len(sa | sb))


def primary_entity(article):
    return (article.entities or [None])[0]


def _article_fingerprint(article) -> str | None:
    """Generate fingerprint for an article."""
    cat = getattr(article, "category", None)
    entities = getattr(article, "entities", None) or []
    keywords = getattr(article, "keywords", None) or []
    dt = getattr(article, "published_at", None)
    return generate_fingerprint(
        category=cat,
        dt=dt,
        entities=list(entities) if isinstance(entities, (list, set)) else list(entities),
        keywords=list(keywords) if isinstance(keywords, (list, set)) else list(keywords),
    )


def _event_article_fingerprints(articles) -> list[str]:
    return [fp for a in articles if (fp := _article_fingerprint(a))]


def cluster_events(articles, now=None):
    now = now or datetime.now(timezone.utc)
    events = []
    candidates = [a for a in articles if not a.is_duplicate and now - a.published_at <= timedelta(hours=24)]
    for a in candidates:
        placed = False
        afp = _article_fingerprint(a)
        for ev in events:
            head = ev.articles[0]
            # Try fingerprint match first (>= 0.8 = same event)
            efp = ev.event_fingerprint
            if afp and efp and fingerprint_overlap(afp, efp) >= 0.8:
                ev.articles.append(a)
                ev.keywords.update(a.keywords)
                ev.entities.update(a.entities)
                placed = True
                break

            if placed:
                break

            # Fallback: title similarity match
            title_match = (
                fuzz.token_set_ratio(
                    a.normalized_title or a.title,
                    head.normalized_title or head.title
                ) >= 88
                and abs(a.published_at - head.published_at) <= timedelta(hours=48)
            )
            if title_match:
                ev.articles.append(a)
                ev.keywords.update(a.keywords)
                ev.entities.update(a.entities)
                placed = True
                break

            # Fallback: keyword overlap + entity match
            kw_match = (
                keyword_overlap(a.keywords, ev.keywords) >= 0.5
                and primary_entity(a)
                and primary_entity(a) in ev.entities
            )
            if kw_match:
                ev.articles.append(a)
                ev.keywords.update(a.keywords)
                ev.entities.update(a.entities)
                placed = True
                break

        if not placed:
            new_event = Event(
                title=a.title,
                articles=[a],
                keywords=set(a.keywords),
                entities=set(a.entities),
                event_fingerprint=afp,
            )
            events.append(new_event)

    # Update event_fingerprint for all events
    for ev in events:
        if not ev.event_fingerprint:
            fps = _event_article_fingerprints(ev.articles)
            ev.event_fingerprint = fps[0] if fps else None

    return events