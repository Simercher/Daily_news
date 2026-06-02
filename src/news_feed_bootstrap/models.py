from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .utils import utc_now


class PipelineModel(BaseModel):
    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)


class SeedSource(PipelineModel):
    id: str
    name: str
    type: Literal[
        "opml",
        "rss",
        "text",
        "html_index",
        "html_feed_index",
        "feed_discovery",
        "google_news_rss",
        "generated_rss",
        "github_page",
        "web_directory",
        "official_api",
    ]
    url: str
    fallback_type: Literal["rss", "google_news_rss", "html_index", "official_api", "none"] | None = None
    fetch_status: Literal["active", "degraded", "fallback", "inactive", "error"] = "active"
    last_success_at: datetime | None = None
    error_count: int = 0
    degraded: bool = False
    repository: str | None = None
    priority: Literal["high", "medium_high", "medium", "low"] = "medium"
    trust_tier: Literal[
        "primary",
        "major_media",
        "specialist",
        "aggregator",
        "third_party_generated",
        "unknown",
    ] = "unknown"
    source_tier: Literal["tier1", "tier2", "tier3", "unknown"] = "unknown"
    source_role: Literal[
        "first_party",
        "official",
        "major_media",
        "specialist",
        "aggregator",
        "community",
        "unknown",
    ] = "unknown"
    source_format: Literal[
        "rss",
        "atom",
        "opml",
        "html_feed_index",
        "html_index",
        "feed_discovery",
        "google_news_rss",
        "official_api",
        "text",
        "generated_rss",
        "unknown",
    ] = "unknown"
    language: str | None = None
    region: str | None = None
    topics: list[str] = Field(default_factory=list)
    dedupe_group: str | None = None
    requires_tolerant_parser: bool = False
    fetch_interval_minutes: int = 360
    commercial_use_risk: Literal["low", "medium", "high", "unknown"] = "unknown"
    enabled: bool = True
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
    trust_tier: str | None = None
    source_tier: str | None = None
    source_role: str | None = None
    source_format: str | None = None
    dedupe_group: str | None = None
    commercial_use_risk: str | None = None
    collector: str = "local_feedparser"
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
    trust_tier: str | None = None
    source_tier: str | None = None
    source_role: str | None = None
    source_format: str | None = None
    dedupe_group: str | None = None
    commercial_use_risk: str | None = None
    collector: str = "local_feedparser"
    source_id: str | None = None
    source_name: str | None = None
    feed_title: str | None = None
    official_source: bool = False
    fetch_status: Literal["active", "degraded", "fallback", "inactive", "error"] = "active"
    last_success_at: datetime | None = None
    error_count: int = 0
    degraded: bool = False
    fallback_source_id: str | None = None
    fallback_source_type: str | None = None
    last_published_at: datetime | None = None
    checked_at: datetime = Field(default_factory=utc_now)


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
    fetch_status: Literal["rss_only", "success", "paywall", "blocked", "parse_failed", "http_error", "skipped", "fallback", "degraded"]
    collector: str = "local_feedparser"
    official_source: bool = False
    language: str | None = None
    topics: list[str] = Field(default_factory=list)
    trust_tier: str | None = None
    source_tier: str | None = None
    source_role: str | None = None
    source_format: str | None = None
    source_id: str | None = None
    dedupe_key: str | None = None
    confidence: Literal["high", "medium", "low"] = "medium"
    importance_score: float | None = None
