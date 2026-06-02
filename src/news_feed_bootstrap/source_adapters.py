from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Callable
from urllib.parse import parse_qs, urlparse

import feedparser
import requests

from .dedup import compute_item_id, normalize_url
from .models import ActiveFeed, NewsItem
from .utils import TIMEOUT, USER_AGENT, parse_datetime, utc_now


@dataclass(slots=True)
class FetchResult:
    items: list[NewsItem] = field(default_factory=list)
    fetch_status: str = "success"
    error: str | None = None
    degraded: bool = False


@dataclass(slots=True)
class SourceAdapter:
    source_type: str
    fetch: Callable[[ActiveFeed, int, object], FetchResult]
    fallback_type: str | None = None


NEWS_GOOGLE_HOSTS = {"news.google.com"}
DEFAULT_SOURCE_RETRY_LIMIT = 3


def _entry_content(entry: dict) -> str | None:
    if entry.get("content"):
        parts = [part.get("value", "") for part in entry.get("content", []) if isinstance(part, dict)]
        return "\n".join(part for part in parts if part) or None
    return entry.get("content:encoded")


def _entry_url(entry: dict, fallback_url: str) -> str:
    if entry.get("feedburner_origlink"):
        return entry["feedburner_origlink"]
    if entry.get("links"):
        for link in entry.get("links", []):
            if isinstance(link, dict) and link.get("rel") == "alternate" and link.get("href"):
                return link["href"]
    return entry.get("link") or entry.get("id") or fallback_url


def _google_news_original_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.lower().endswith("news.google.com"):
        qs = parse_qs(parsed.query)
        for key in ("url", "q", "u"):
            if qs.get(key):
                candidate = qs[key][0]
                if candidate.startswith("http"):
                    return candidate
    return None


def _build_item(feed: ActiveFeed, entry: dict, fetched_at, collector: str, url: str, fetch_status: str) -> NewsItem:
    canonical = normalize_url(url)
    summary = entry.get("summary") or entry.get("description")
    content = _entry_content(entry)
    published_at = parse_datetime(entry.get("published") or entry.get("updated")) or fetched_at
    return NewsItem(
        id=compute_item_id(canonical, entry.get("title"), published_at),
        title=entry.get("title") or "(untitled)",
        url=url,
        canonical_url=canonical,
        publisher=feed.publisher,
        feed_url=feed.feed_url,
        published_at=published_at,
        published_at_fallback=parse_datetime(entry.get("published") or entry.get("updated")) is None,
        fetched_at=fetched_at,
        rss_summary=summary,
        rss_content=content,
        content_level="full_text" if content and len(content) >= 1500 else "partial" if (content or summary or "") and len(content or summary or "") >= 500 else "summary_only",
        fetch_status=fetch_status,  # type: ignore[arg-type]
        collector=collector,
        official_source=bool(feed.official_source),
        language=feed.language,
        topics=feed.topics,
        trust_tier=feed.trust_tier,
        source_tier=feed.source_tier,
        source_role=feed.source_role,
        source_format=feed.source_format,
        source_id=feed.source_id,
        dedupe_key=canonical,
        confidence="low" if collector == "google_news_rss" else "medium",
    )


def fetch_rss(feed: ActiveFeed, since_hours: int, fetched_at) -> FetchResult:
    try:
        response = requests.get(feed.feed_url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
    except requests.RequestException as exc:
        return FetchResult(fetch_status="http_error", error=str(exc))
    cutoff = fetched_at - timedelta(hours=since_hours)
    items: list[NewsItem] = []
    for entry in parsed.entries:
        published_at = parse_datetime(entry.get("published") or entry.get("updated")) or fetched_at
        if published_at < cutoff:
            continue
        url = _entry_url(entry, feed.feed_url)
        items.append(_build_item(feed, entry, fetched_at, "local_feedparser", url, "rss_only"))
    return FetchResult(items=items)


def fetch_google_news_rss(feed: ActiveFeed, since_hours: int, fetched_at) -> FetchResult:
    result = fetch_rss(feed, since_hours, fetched_at)
    for item in result.items:
        original = _google_news_original_url(item.url)
        if original:
            item.url = original
            item.canonical_url = normalize_url(original)
            item.dedupe_key = item.canonical_url
    for item in result.items:
        item.confidence = "low"
    return result


def skip_unsupported_source(_: ActiveFeed, __: int, ___) -> FetchResult:
    return FetchResult(fetch_status="skipped", degraded=False)


ADAPTERS: dict[str, SourceAdapter] = {
    "rss": SourceAdapter("rss", fetch_rss),
    "google_news_rss": SourceAdapter("google_news_rss", fetch_google_news_rss, fallback_type="rss"),
    "html_index": SourceAdapter("html_index", skip_unsupported_source),
    "official_api": SourceAdapter("official_api", skip_unsupported_source),
}


def adapter_for(feed: ActiveFeed) -> SourceAdapter:
    return ADAPTERS.get(feed.source_format or "rss", ADAPTERS["rss"])
