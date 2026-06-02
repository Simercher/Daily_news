from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from rapidfuzz import fuzz

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

def keyword_overlap(a,b):
    sa=set(a or []); sb=set(b or [])
    return len(sa&sb)/max(1,len(sa|sb))

def primary_entity(article):
    return (article.entities or [None])[0]

def cluster_events(articles, now=None):
    now = now or datetime.now(timezone.utc); events=[]
    candidates=[a for a in articles if not a.is_duplicate and now-a.published_at <= timedelta(hours=24)]
    for a in candidates:
        placed=False
        for ev in events:
            head=ev.articles[0]
            title_match=fuzz.token_set_ratio(a.normalized_title or a.title, head.normalized_title or head.title)>=88 and abs(a.published_at-head.published_at)<=timedelta(hours=48)
            kw_match=keyword_overlap(a.keywords, ev.keywords)>=0.5 and primary_entity(a) and primary_entity(a) in ev.entities
            if title_match or kw_match:
                ev.articles.append(a); ev.keywords.update(a.keywords); ev.entities.update(a.entities); placed=True; break
        if not placed:
            events.append(Event(title=a.title, articles=[a], keywords=set(a.keywords), entities=set(a.entities)))
    return events
