from __future__ import annotations

import importlib
from pathlib import Path

import requests

import news_feed_bootstrap.utils as utils
from news_feed_bootstrap.feed_fetcher import fetch_feed_items
from news_feed_bootstrap.utils import parse_datetime


def test_timeout_can_be_configured_with_environment(monkeypatch) -> None:
    monkeypatch.setenv("NEWS_FEED_TIMEOUT_SECONDS", "3")

    reloaded = importlib.reload(utils)

    assert reloaded.TIMEOUT == 3.0


class FakeResponse:
    status_code = 200
    content = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Test</title>
    <item><title>No Date</title><link>https://example.com/no-date</link><description>Summary</description></item>
    </channel></rss>"""

    def raise_for_status(self) -> None:
        return None


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
