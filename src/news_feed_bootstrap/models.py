from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PipelineModel(BaseModel):
    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)


class SeedSource(PipelineModel):
    id: str
    name: str
    type: Literal["opml", "text", "github_page", "web_directory"]
    url: str
    repository: str | None = None
    priority: Literal["high", "medium_high", "medium", "low"] = "medium"
    topics: list[str] = Field(default_factory=list)
    notes: str | None = None


class FeedCandidate(PipelineModel):
    id: str | None = None
    publisher: str | None = None
    feed_url: str
    homepage: str | None = None
    discovered_from: str
    region: str | None = None
    language: str | None = None
    topics: list[str] = Field(default_factory=list)
    priority: str | None = None
    source_id: str | None = None
    source_name: str | None = None


class FeedValidationResult(PipelineModel):
    feed_url: str
    status: Literal["active", "inactive", "parse_failed", "http_error", "blocked"]
    http_status: int | None = None
    content_type: str | None = None
    parse_ok: bool
    feed_title: str | None = None
    entry_count: int
    last_published_at: datetime | None = None
    items_7d: int
    items_30d: int
    has_title_rate: float
    has_link_rate: float
    has_pub_date_rate: float
    duplicate_url_rate: float
    has_summary_rate: float
    has_full_content_rate: float
    checked_at: datetime


class ActiveFeed(PipelineModel):
    publisher: str | None = None
    feed_url: str
    homepage: str | None = None
    language: str | None = None
    region: str | None = None
    topics: list[str] = Field(default_factory=list)
    priority: str | None = None
    source_id: str | None = None
    source_name: str | None = None
    feed_title: str | None = None
    last_published_at: datetime | None = None
    checked_at: datetime


class NewsItem(PipelineModel):
    id: str
    title: str
    url: str
    canonical_url: str | None = None
    publisher: str | None = None
    feed_url: str
    published_at: datetime | None = None
    published_at_fallback: bool = False
    fetched_at: datetime
    rss_summary: str | None = None
    rss_content: str | None = None
    full_text: str | None = None
    content_level: Literal["summary_only", "partial", "full_text"]
    fetch_status: Literal["rss_only", "success", "paywall", "blocked", "parse_failed", "http_error", "skipped"]
    language: str | None = None
    topics: list[str] = Field(default_factory=list)
    importance_score: float | None = None
