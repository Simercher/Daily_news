from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import ARRAY, BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class NewsSource(Base):
    __tablename__ = "news_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="rss")
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    domain: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(16))
    language: Mapped[str | None] = mapped_column(String(16))
    category: Mapped[str | None] = mapped_column(String(64))
    trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    credibility_score: Mapped[float] = mapped_column(Float, default=0.5)
    region: Mapped[str | None] = mapped_column(String(64))
    ownership_type: Mapped[str | None] = mapped_column(String(64))
    source_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc)

    @property
    def type(self) -> str:  # backward-compatible alias
        return self.source_type

    @type.setter
    def type(self, value: str) -> None:
        self.source_type = value


class ArticleModel(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="rss", index=True)
    source_name: Mapped[str | None] = mapped_column(String(255), index=True)
    source_domain: Mapped[str | None] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str | None] = mapped_column(Text, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    content_snippet: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    url_hash: Mapped[str | None] = mapped_column(String(64), nullable=False, index=True)
    language: Mapped[str | None] = mapped_column(String(16))
    country: Mapped[str | None] = mapped_column(String(16))
    category: Mapped[str | None] = mapped_column(String(64), index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    title_hash: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    duplicate_of_article_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("articles.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc)
    # fulltext_status is VARCHAR(32), not an enum. Valid values:
    # not_attempted, extracted, partial, empty, blocked, timeout, error, paywalled
    fulltext_status: Mapped[str | None] = mapped_column(String(32), default="not_attempted")
    fulltext_quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    fulltext_extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fulltext_error_message: Mapped[str | None] = mapped_column(Text)

    duplicate_of: Mapped["ArticleModel | None"] = relationship("ArticleModel", remote_side=[id])

    __table_args__ = (UniqueConstraint("url_hash", name="uq_articles_url_hash"),)

    @property
    def source_id(self) -> str | None:  # backward-compatible alias
        return self.external_id

    @source_id.setter
    def source_id(self, value: str | None) -> None:
        self.external_id = value

    @property
    def content(self) -> str | None:
        return self.content_snippet

    @content.setter
    def content(self, value: str | None) -> None:
        self.content_snippet = value

    @property
    def raw(self) -> dict:
        return self.raw_payload

    @raw.setter
    def raw(self, value: dict) -> None:
        self.raw_payload = value

    @property
    def duplicate_of_id(self) -> int | None:
        return self.duplicate_of_article_id

    @duplicate_of_id.setter
    def duplicate_of_id(self, value: int | None) -> None:
        self.duplicate_of_article_id = value

    @property
    def keywords(self) -> list:
        return (self.raw_payload or {}).get("keywords", [])

    @keywords.setter
    def keywords(self, value: list) -> None:
        payload = dict(self.raw_payload or {})
        payload["keywords"] = value
        self.raw_payload = payload

    @property
    def entities(self) -> list:
        return (self.raw_payload or {}).get("entities", [])

    @entities.setter
    def entities(self, value: list) -> None:
        payload = dict(self.raw_payload or {})
        payload["entities"] = value
        self.raw_payload = payload

    def ensure_utc(self) -> "ArticleModel":
        if self.published_at and self.published_at.tzinfo is None:
            self.published_at = self.published_at.replace(tzinfo=timezone.utc)
        elif self.published_at:
            self.published_at = self.published_at.astimezone(timezone.utc)
        return self


class EventModel(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_title: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64), index=True)
    severity: Mapped[str | None] = mapped_column(String(32))
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, index=True)
    article_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trusted_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    country_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    popular_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    importance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    breaking_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    final_score: Mapped[float] = mapped_column(Float, nullable=False, default=0, index=True)
    # status is VARCHAR(32). Valid values: active, breaking, archived, merged, ignored
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    is_breaking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    breaking_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    keywords: Mapped[list] = mapped_column(ARRAY(String).with_variant(JSON, "sqlite"), nullable=False, default=list)
    entities: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc)

    event_fingerprint: Mapped[str | None] = mapped_column(Text)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    representative_article_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("articles.id", ondelete="SET NULL"))
    last_scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cluster_method: Mapped[str | None] = mapped_column(String(64))

    representative_article: Mapped["ArticleModel | None"] = relationship("ArticleModel", foreign_keys=[representative_article_id])
    breaking_alert_states = relationship("BreakingAlertState", back_populates="event", cascade="all, delete-orphan")

    @property
    def velocity_score(self) -> float:
        return self.breaking_score

    @velocity_score.setter
    def velocity_score(self, value: float) -> None:
        self.breaking_score = value

    @property
    def source_diversity_score(self) -> float:
        return self.popular_score

    @source_diversity_score.setter
    def source_diversity_score(self, value: float) -> None:
        self.popular_score = value

    @property
    def severity_score(self) -> float:
        return self.importance_score

    @severity_score.setter
    def severity_score(self, value: float) -> None:
        self.importance_score = value


class EventArticle(Base):
    __tablename__ = "event_articles"

    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    article_id: Mapped[int] = mapped_column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True, index=True)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_representative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="rss", index=True)
    source_name: Mapped[str | None] = mapped_column(String(255), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", index=True)
    lookback_hours: Mapped[int | None] = mapped_column(Integer)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc)

    @property
    def source(self) -> str | None:
        return self.source_name

    @source.setter
    def source(self, value: str | None) -> None:
        self.source_name = value

    @property
    def error(self) -> str | None:
        return self.error_message

    @error.setter
    def error(self, value: str | None) -> None:
        self.error_message = value


class BreakingAlertState(Base):
    __tablename__ = "breaking_alert_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alert_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_breaking_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_breaking_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_trusted_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_article_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # status is VARCHAR(32). Valid values: active, cooldown, updated, resolved, ignored
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now_utc, onupdate=now_utc)

    event = relationship("EventModel", back_populates="breaking_alert_states")
