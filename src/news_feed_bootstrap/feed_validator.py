from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

import feedparser
import requests

from .models import FeedValidationResult
from .utils import TIMEOUT, USER_AGENT, is_blocked_response, utc_now, write_jsonl


def _entry_datetime(entry: dict) -> object | None:
    return entry.get("published") or entry.get("updated") or entry.get("created")


def _safe_parse_date(value: object) -> object | None:
    if not value:
        return None
    if hasattr(value, "tm_year"):
        return datetime(*value[:6], tzinfo=UTC)
    try:
        parsed = parsedate_to_datetime(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def validate_feed(feed_url: str) -> FeedValidationResult:
    checked_at = utc_now()
    try:
        response = requests.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    except requests.RequestException:
        return FeedValidationResult(
            feed_url=feed_url,
            status="http_error",
            http_status=None,
            content_type=None,
            parse_ok=False,
            feed_title=None,
            entry_count=0,
            last_published_at=None,
            items_7d=0,
            items_30d=0,
            has_title_rate=0,
            has_link_rate=0,
            has_pub_date_rate=0,
            duplicate_url_rate=0,
            has_summary_rate=0,
            has_full_content_rate=0,
            checked_at=checked_at,
        )

    content_type = response.headers.get("content-type")
    if is_blocked_response(response.status_code, response.text):
        status = "blocked"
    elif response.status_code >= 400:
        status = "http_error"
    else:
        status = "active"

    parsed = feedparser.parse(response.content)
    parse_ok = not parsed.bozo and bool(parsed.entries)
    entries = list(parsed.entries)
    if status == "active" and not parse_ok:
        status = "parse_failed"

    total = len(entries)
    dates = [
        _safe_parse_date(entry.get("published_parsed") or entry.get("updated_parsed") or _entry_datetime(entry))
        for entry in entries
    ]
    dates = [date for date in dates if date is not None]
    last_published_at = max(dates) if dates else None
    items_7d = sum(1 for date in dates if checked_at - date <= timedelta(days=7))
    items_30d = sum(1 for date in dates if checked_at - date <= timedelta(days=30))
    if status == "active" and parse_ok and items_30d == 0:
        status = "inactive"
    links = [entry.get("link") for entry in entries if entry.get("link")]
    duplicate_url_rate = 0 if not links else 1 - (len(set(links)) / len(links))

    def rate(predicate) -> float:
        return 0 if total == 0 else sum(1 for entry in entries if predicate(entry)) / total

    result = FeedValidationResult(
        feed_url=feed_url,
        status=status,
        http_status=response.status_code,
        content_type=content_type,
        parse_ok=parse_ok,
        feed_title=parsed.feed.get("title"),
        entry_count=total,
        last_published_at=last_published_at,
        items_7d=items_7d,
        items_30d=items_30d,
        has_title_rate=rate(lambda e: bool(e.get("title"))),
        has_link_rate=rate(lambda e: bool(e.get("link"))),
        has_pub_date_rate=rate(
            lambda e: bool(
                e.get("published")
                or e.get("updated")
                or e.get("published_parsed")
                or e.get("updated_parsed")
            )
        ),
        duplicate_url_rate=duplicate_url_rate,
        has_summary_rate=rate(lambda e: bool(e.get("summary") or e.get("description"))),
        has_full_content_rate=rate(lambda e: bool(e.get("content"))),
        checked_at=checked_at,
    )
    return result


def write_feed_health(results: list[FeedValidationResult], path: str = "data/feed_health.jsonl") -> None:
    write_jsonl(path, results)
