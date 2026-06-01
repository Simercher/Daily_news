from __future__ import annotations

from pathlib import Path

import requests

from news_feed_bootstrap.feed_fetcher import fetch_feed_items


class FakeResponse:
    status_code = 200
    content = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Test</title>
    <item><title>No Date</title><link>https://example.com/no-date</link><description>Summary</description></item>
    </channel></rss>"""

    def raise_for_status(self) -> None:
        return None


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
