from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, JSON, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from datetime import datetime, timezone

class Base(DeclarativeBase): pass

def now_utc(): return datetime.now(timezone.utc)

class NewsSource(Base):
    __tablename__='news_sources'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    name: Mapped[str]=mapped_column(String(255), unique=True)
    type: Mapped[str]=mapped_column(String(50))
    url: Mapped[str|None]=mapped_column(Text)
    country: Mapped[str|None]=mapped_column(String(10))
    language: Mapped[str|None]=mapped_column(String(10))
    category: Mapped[str|None]=mapped_column(String(64))
    enabled: Mapped[bool]=mapped_column(Boolean, default=True)

class ArticleModel(Base):
    __tablename__='articles'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)

    def ensure_utc(self):
        if self.published_at and self.published_at.tzinfo is None:
            self.published_at = self.published_at.replace(tzinfo=timezone.utc)
        elif self.published_at:
            self.published_at = self.published_at.astimezone(timezone.utc)
        return self
    source_id: Mapped[str|None]=mapped_column(String(128))
    source_name: Mapped[str|None]=mapped_column(String(255))
    title: Mapped[str]=mapped_column(Text)
    normalized_title: Mapped[str|None]=mapped_column(Text, index=True)
    url: Mapped[str]=mapped_column(Text)
    canonical_url: Mapped[str|None]=mapped_column(Text)
    url_hash: Mapped[str|None]=mapped_column(String(64), index=True)
    published_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), index=True)
    author: Mapped[str|None]=mapped_column(String(255))
    description: Mapped[str|None]=mapped_column(Text)
    content: Mapped[str|None]=mapped_column(Text)
    image_url: Mapped[str|None]=mapped_column(Text)
    language: Mapped[str|None]=mapped_column(String(10))
    country: Mapped[str|None]=mapped_column(String(10))
    category: Mapped[str|None]=mapped_column(String(64))
    entities: Mapped[list]=mapped_column(JSON, default=list)
    keywords: Mapped[list]=mapped_column(JSON, default=list)
    raw: Mapped[dict]=mapped_column(JSON, default=dict)
    is_duplicate: Mapped[bool]=mapped_column(Boolean, default=False)
    duplicate_of_id: Mapped[int|None]=mapped_column(Integer, ForeignKey('articles.id'))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__=(UniqueConstraint('url_hash', name='uq_articles_url_hash'),)

class EventModel(Base):
    __tablename__='events'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    title: Mapped[str]=mapped_column(Text)
    event_date: Mapped[datetime]=mapped_column(DateTime(timezone=True), index=True)
    keywords: Mapped[list]=mapped_column(JSON, default=list)
    entities: Mapped[list]=mapped_column(JSON, default=list)
    article_count: Mapped[int]=mapped_column(Integer, default=0)
    velocity_score: Mapped[float]=mapped_column(Float, default=0)
    source_diversity_score: Mapped[float]=mapped_column(Float, default=0)
    severity_score: Mapped[float]=mapped_column(Float, default=0)
    final_score: Mapped[float]=mapped_column(Float, default=0)
    is_breaking: Mapped[bool]=mapped_column(Boolean, default=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now_utc)

class EventArticle(Base):
    __tablename__='event_articles'
    event_id: Mapped[int]=mapped_column(ForeignKey('events.id'), primary_key=True)
    article_id: Mapped[int]=mapped_column(ForeignKey('articles.id'), primary_key=True)
    relevance_score: Mapped[float]=mapped_column(Float, default=1)

class CollectionRun(Base):
    __tablename__='collection_runs'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    source: Mapped[str]=mapped_column(String(128))
    started_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=now_utc)
    finished_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    status: Mapped[str]=mapped_column(String(32), default='running')
    fetched_count: Mapped[int]=mapped_column(Integer, default=0)
    inserted_count: Mapped[int]=mapped_column(Integer, default=0)
    error: Mapped[str|None]=mapped_column(Text)
