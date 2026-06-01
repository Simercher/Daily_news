from __future__ import annotations

from datetime import UTC, datetime

from tqdm import tqdm

from .config import read_yaml, resolve_path
from .classifier import run_article_classifier
from .dedup import deduplicate_items, normalize_url
from .feed_fetcher import fetch_feed_items
from .feed_validator import validate_feed, write_feed_health
from .models import ActiveFeed, FeedCandidate, NewsItem
from .opml_importer import import_seed_lists, write_active_opml, write_feeds_opml
from .source_classification import is_official_source
from .utils import read_jsonl, utc_now, write_json, write_jsonl


def bootstrap_candidates(config_path: str = "configs/seed_sources.yaml") -> list[FeedCandidate]:
    feeds = import_seed_lists(config_path)
    payload = [feed.model_dump(mode="json") for feed in feeds]
    write_json("data/imported_feeds.json", {"feeds": payload})
    write_feeds_opml(payload, "data/imported_feeds.opml", "Daily News Imported Feeds")
    return feeds


def build_active_feeds(
    candidates_path: str = "data/imported_feeds.json",
    active_json_path: str = "data/active_feeds.json",
    active_opml_path: str = "data/active_feeds.opml",
    inactive_json_path: str = "data/inactive_feeds.json",
    show_progress: bool = True,
) -> list[ActiveFeed]:
    feeds = [FeedCandidate(**row) for row in (read_yaml(candidates_path, {"feeds": []}).get("feeds") or [])]
    results = [
        validate_feed(feed.feed_url)
        for feed in tqdm(feeds, desc="health checking feeds", disable=not show_progress)
    ]
    write_feed_health(results)
    health_by_url = {result.feed_url: result for result in results}
    active: list[ActiveFeed] = []
    inactive: list[dict] = []

    for feed in feeds:
        health = health_by_url.get(feed.feed_url)
        if not health or health.status != "active":
            inactive.append(
                {
                    **feed.model_dump(mode="json"),
                    "health": health.model_dump(mode="json") if health else None,
                }
            )
            continue
        active.append(
            ActiveFeed(
                publisher=feed.publisher,
                feed_url=feed.feed_url,
                homepage=feed.homepage,
                language=feed.language,
                region=feed.region,
                topics=feed.topics,
                priority=feed.priority,
                trust_tier=feed.trust_tier,
                source_tier=feed.source_tier,
                source_role=feed.source_role,
                source_format=feed.source_format,
                dedupe_group=feed.dedupe_group,
                commercial_use_risk=feed.commercial_use_risk,
                collector=feed.collector,
                source_id=feed.source_id,
                source_name=feed.source_name,
                feed_title=health.feed_title,
                official_source=is_official_source(
                    feed_url=feed.feed_url,
                    homepage=feed.homepage,
                    publisher=feed.publisher,
                    feed_title=health.feed_title,
                ),
                last_published_at=health.last_published_at,
                checked_at=health.checked_at,
            )
        )

    payload = [feed.model_dump(mode="json") for feed in active]
    write_json(active_json_path, {"feeds": payload})
    write_json(inactive_json_path, {"feeds": inactive})
    write_active_opml(payload, active_opml_path)
    return active


def run_local_fetch(since_hours: int = 24, active_feeds_path: str = "data/active_feeds.json") -> list:
    items = fetch_feed_items(active_feeds_path=active_feeds_path, since_hours=since_hours)
    write_jsonl("data/news_items_raw.jsonl", items)
    return items


def _model_item_for_downstream(item: NewsItem | dict, active_by_url: dict[str, dict]) -> dict:
    data = item.model_dump(mode="json") if isinstance(item, NewsItem) else item
    normalized_url = normalize_url(data.get("canonical_url") or data["url"])
    feed = active_by_url.get(data["feed_url"], {})
    topics = data.get("topics") or feed.get("topics") or []
    official_source = bool(data.get("official_source") or feed.get("official_source", False))
    return {
        "id": data["id"],
        "title": data["title"],
        "url": data["url"],
        "canonical_url": data.get("canonical_url") or data.get("url"),
        "normalized_url": normalized_url,
        "feed_url": data["feed_url"],
        "feed_title": feed.get("feed_title") or data.get("publisher"),
        "source_seed_id": feed.get("source_id"),
        "source_seed_name": feed.get("source_name"),
        "trust_tier": feed.get("trust_tier") or data.get("trust_tier"),
        "source_tier": feed.get("source_tier") or data.get("source_tier"),
        "source_role": feed.get("source_role") or data.get("source_role"),
        "source_format": feed.get("source_format") or data.get("source_format"),
        "dedupe_group": feed.get("dedupe_group"),
        "dedupe_key": data.get("dedupe_key") or normalized_url,
        "category": topics[0] if topics else None,
        "published_at": data.get("published_at"),
        "fetched_at": data.get("fetched_at"),
        "summary": data.get("rss_summary"),
        "content": data.get("rss_content") or data.get("full_text"),
        "author": data.get("author"),
        "tags": topics,
        "content_level": data.get("content_level"),
        "language": data.get("language"),
        "collector": data.get("collector", "local_feedparser"),
        "official_source": official_source,
        "raw": data,
    }


def dedup_raw_items(
    input_path: str = "data/news_items_raw.jsonl",
    output_path: str = "data/news_items_deduped.jsonl",
    active_feeds_path: str = "data/active_feeds.json",
) -> list[dict]:
    rows = read_jsonl(input_path)
    items = [NewsItem(**row) for row in rows]
    deduped = deduplicate_items(items)
    active = read_yaml(active_feeds_path, {"feeds": []}).get("feeds") or []
    active_by_url = {feed["feed_url"]: feed for feed in active}
    downstream_rows = [_model_item_for_downstream(item, active_by_url) for item in deduped]
    write_jsonl(output_path, downstream_rows)
    return downstream_rows


def run_bootstrap(config_path: str = "configs/seed_sources.yaml", show_progress: bool = True) -> list[ActiveFeed]:
    bootstrap_candidates(config_path)
    return build_active_feeds(show_progress=show_progress)


def run_all(mode: str = "local", since_hours: int = 24, config_path: str = "configs/seed_sources.yaml") -> dict:
    if mode != "local":
        raise ValueError(
            "MCP fetch is not implemented yet; generate an MCP config hint and use local mode as fallback."
        )
    active = run_bootstrap(config_path)
    raw = run_local_fetch(since_hours=since_hours)
    deduped = dedup_raw_items()
    labels = run_article_classifier(input_path="data/news_items_deduped.jsonl", output_path="data/news_item_labels.jsonl")
    return {
        "active_feeds": len(active),
        "raw_items": len(raw),
        "deduped_items": len(deduped),
        "labeled_items": len(labels),
    }


def path_is_stale(path: str, max_age_hours: int = 24) -> bool:
    resolved = resolve_path(path)
    if not resolved.exists():
        return True
    age_seconds = utc_now().timestamp() - resolved.stat().st_mtime
    return age_seconds > max_age_hours * 3600


def line_count(path: str) -> int:
    resolved = resolve_path(path)
    if not resolved.exists():
        return 0
    with resolved.open("r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def file_info(path: str) -> dict:
    resolved = resolve_path(path)
    exists = resolved.exists()
    return {
        "path": path,
        "exists": exists,
        "modified_at": (
            datetime.fromtimestamp(resolved.stat().st_mtime, tz=UTC).isoformat()
            if exists
            else None
        ),
        "size_bytes": resolved.stat().st_size if exists else 0,
    }


def project_status() -> dict:
    imported = read_yaml("data/imported_feeds.json", {"feeds": []}).get("feeds") or []
    active = read_yaml("data/active_feeds.json", {"feeds": []}).get("feeds") or []
    inactive = read_yaml("data/inactive_feeds.json", {"feeds": []}).get("feeds") or []
    outputs = [
        "data/imported_feeds.json",
        "data/imported_feeds.opml",
        "data/feed_health.jsonl",
        "data/active_feeds.json",
        "data/active_feeds.opml",
        "data/inactive_feeds.json",
        "data/news_items_raw.jsonl",
        "data/news_items_deduped.jsonl",
        "data/news_item_labels.jsonl",
        "data/news_item_fulltext.jsonl",
        "data/logs/mcp_config_hint.jsonl",
    ]
    return {
        "outputs": {path: path for path in outputs},
        "stats": {
            "imported_feeds": len(imported),
            "active_feeds": len(active),
            "inactive_feeds": len(inactive),
            "raw_items": line_count("data/news_items_raw.jsonl"),
            "deduped_items": line_count("data/news_items_deduped.jsonl"),
            "labeled_items": line_count("data/news_item_labels.jsonl"),
            "fulltext_items": line_count("data/news_item_fulltext.jsonl"),
        },
        "files": {path: file_info(path) for path in outputs},
    }
