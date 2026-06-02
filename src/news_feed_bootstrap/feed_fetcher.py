from __future__ import annotations

from datetime import timedelta

from .config import read_yaml
from .models import ActiveFeed, NewsItem
from .source_adapters import DEFAULT_SOURCE_RETRY_LIMIT, adapter_for
from .utils import utc_now, write_json, write_jsonl


def fetch_feed_items(
    active_feeds_path: str = "data/active_feeds.json",
    since_hours: int = 24,
    output_path: str = "data/news_items_raw.jsonl",
) -> list[NewsItem]:
    config = read_yaml(active_feeds_path, {"feeds": []})
    fetched_at = utc_now()
    cutoff = fetched_at - timedelta(hours=since_hours)
    items: list[NewsItem] = []
    updated_feeds: list[dict] = []

    for feed_row in config.get("feeds", []):
        feed = ActiveFeed(**feed_row)
        adapter = adapter_for(feed)
        result = adapter.fetch(feed, since_hours, fetched_at)

        errors = feed.error_count + (1 if result.error else 0)
        degraded = bool(result.degraded or errors >= DEFAULT_SOURCE_RETRY_LIMIT)
        fetch_status = "degraded" if degraded else ("fallback" if adapter.fallback_type else "active")
        if result.items and not result.error:
            errors = 0
            degraded = False
            fetch_status = "active"

        feed_state = feed.model_copy(update={
            "fetch_status": fetch_status,
            "error_count": errors,
            "degraded": degraded,
            "last_success_at": fetched_at if result.items and not result.error else feed.last_success_at,
            "fallback_source_type": adapter.fallback_type,
            "fallback_source_id": feed.source_id if adapter.fallback_type else feed.fallback_source_id,
        })
        updated_feeds.append(feed_state.model_dump(mode="json"))

        for item in result.items:
            if item.published_at and item.published_at < cutoff:
                continue
            items.append(item)

    write_jsonl(output_path, items)
    write_json(active_feeds_path, {"feeds": updated_feeds})
    return items
