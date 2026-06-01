from __future__ import annotations

from datetime import timedelta

import feedparser
import requests

from .config import read_yaml
from .dedup import compute_item_id, normalize_url
from .mcp_fetcher import mcp_server_ready
from .models import NewsItem
from .source_classification import is_official_source
from .utils import TIMEOUT, USER_AGENT, parse_datetime, utc_now, write_jsonl


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


def _content_level(summary: str | None, content: str | None) -> str:
    text = content or summary or ""
    if len(text) >= 1500:
        return "full_text"
    if len(text) >= 500:
        return "partial"
    return "summary_only"


def fetch_feed_items(
    active_feeds_path: str = "data/active_feeds.json",
    since_hours: int = 24,
    output_path: str = "data/news_items_raw.jsonl",
) -> list[NewsItem]:
    config = read_yaml(active_feeds_path, {"feeds": []})
    fetched_at = utc_now()
    cutoff = fetched_at - timedelta(hours=since_hours)
    items: list[NewsItem] = []
    use_mcp = mcp_server_ready()
    if use_mcp:
        # MCP-first path: if the configured MCP server is present we can hand off
        # upstream collection here later. This MVP keeps the repository runnable
        # by retaining the local fetch implementation below as a fallback.
        pass
    for feed in config.get("feeds", []):
        try:
            response = requests.get(feed["feed_url"], headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
            response.raise_for_status()
        except requests.RequestException:
            continue
        parsed = feedparser.parse(response.content)
        for entry in parsed.entries:
            parsed_published_at = parse_datetime(entry.get("published") or entry.get("updated"))
            published_at_fallback = parsed_published_at is None
            published_at = parsed_published_at or fetched_at
            effective_time = published_at
            if effective_time < cutoff:
                continue
            url = _entry_url(entry, feed["feed_url"])
            canonical = normalize_url(url)
            summary = entry.get("summary") or entry.get("description")
            content = _entry_content(entry)
            official_source = feed.get("official_source")
            if official_source is None:
                official_source = is_official_source(
                    feed_url=feed.get("feed_url"),
                    homepage=feed.get("homepage"),
                    publisher=feed.get("publisher"),
                    feed_title=feed.get("feed_title"),
                )
            items.append(
                NewsItem(
                    id=compute_item_id(canonical, entry.get("title"), published_at),
                    title=entry.get("title") or "(untitled)",
                    url=url,
                    canonical_url=canonical,
                    publisher=feed.get("publisher"),
                    feed_url=feed["feed_url"],
                    published_at=published_at,
                    published_at_fallback=published_at_fallback,
                    fetched_at=fetched_at,
                    rss_summary=summary,
                    rss_content=content,
                    content_level=_content_level(summary, content),
                    fetch_status="rss_only",
                    collector=feed.get("collector", "local_feedparser"),
                    official_source=bool(official_source),
                    language=feed.get("language"),
                    topics=feed.get("topics") or [],
                    trust_tier=feed.get("trust_tier"),
                    source_id=feed.get("source_id"),
                    dedupe_key=canonical,
                    confidence="low" if feed.get("collector") == "google_news_rss" else "medium",
                )
            )
    write_jsonl(output_path, items)
    return items
