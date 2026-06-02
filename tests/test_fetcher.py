from __future__ import annotations

import importlib
from pathlib import Path

import requests

import news_feed_bootstrap.utils as utils
from news_feed_bootstrap.feed_fetcher import fetch_feed_items
from news_feed_bootstrap.source_adapters import adapter_for
from news_feed_bootstrap.models import ActiveFeed
from news_feed_bootstrap.utils import parse_datetime


class FakeResponse:
    status_code = 200
    content = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Test</title>
    <item><title>No Date</title><link>https://example.com/no-date</link><description>Summary</description></item>
    </channel></rss>"""

    def raise_for_status(self) -> None:
        return None


def test_timeout_can_be_configured_with_environment(monkeypatch) -> None:
    monkeypatch.setenv("NEWS_FEED_TIMEOUT_SECONDS", "3")

    reloaded = importlib.reload(utils)

    assert reloaded.TIMEOUT == 3.0


def test_parse_datetime_assumes_utc_for_naive_strings() -> None:
    parsed = parse_datetime("2026-06-01 10:00:00")

    assert parsed is not None
    assert parsed.tzinfo is not None


def test_fetch_feed_items_records_published_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse())
    active = tmp_path / "active.yaml"
    output = tmp_path / "items.jsonl"
    active.write_text(
        "feeds:\n"
        "  - publisher: Example\n"
        "    feed_url: https://example.com/rss.xml\n",
        encoding="utf-8",
    )

    items = fetch_feed_items(str(active), since_hours=24, output_path=str(output))

    assert len(items) == 1
    assert items[0].published_at is not None
    assert items[0].published_at_fallback is True
    assert items[0].collector == "local_feedparser"


def test_fetch_feed_items_marks_official_source_from_active_feed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse())
    active = tmp_path / "active.yaml"
    output = tmp_path / "items.jsonl"
    active.write_text(
        "feeds:\n"
        "  - publisher: Example\n"
        "    feed_url: https://example.com/rss.xml\n"
        "    official_source: true\n",
        encoding="utf-8",
    )

    items = fetch_feed_items(str(active), since_hours=24, output_path=str(output))

    assert len(items) == 1
    assert items[0].official_source is True
    assert '"official_source": true' in output.read_text(encoding="utf-8")


def test_official_api_adapter_is_interface_only() -> None:
    feed = ActiveFeed(feed_url="https://example.com/api", source_format="official_api")

    result = adapter_for(feed).fetch(feed, 24, utils.utc_now())

    assert result.items == []
    assert result.fetch_status == "skipped"
    assert result.degraded is False


def test_fetch_feed_items_updates_feed_state_on_failure(monkeypatch, tmp_path: Path) -> None:
    def boom(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", boom)
    active = tmp_path / "active.json"
    output = tmp_path / "items.jsonl"
    active.write_text('{"feeds":[{"publisher":"Example","feed_url":"https://example.com/rss.xml","error_count":2}]}', encoding="utf-8")

    items = fetch_feed_items(str(active), since_hours=24, output_path=str(output))

    assert items == []
    updated = active.read_text(encoding="utf-8")
    assert '"degraded": true' in updated
    assert '"error_count": 3' in updated


def test_google_news_items_attempt_original_url_resolution() -> None:
    from news_feed_bootstrap.source_adapters import _google_news_original_url

    assert _google_news_original_url("https://news.google.com/rss/articles/CBMi...?...&url=https%3A%2F%2Fexample.com%2Fstory") == "https://example.com/story"
