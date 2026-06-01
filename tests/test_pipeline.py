from __future__ import annotations

from datetime import UTC, datetime

from news_feed_bootstrap.models import NewsItem
from news_feed_bootstrap.pipeline import _model_item_for_downstream


def test_downstream_item_keeps_collector() -> None:
    item = NewsItem(
        id="abc",
        title="Title",
        url="https://example.com/a?utm_source=x",
        feed_url="https://example.com/rss.xml",
        fetched_at=datetime.now(UTC),
        content_level="summary_only",
        fetch_status="rss_only",
        collector="mcp:imprvhub_mcp_rss_aggregator",
    )

    row = _model_item_for_downstream(item, {"https://example.com/rss.xml": {"topics": ["news"]}})

    assert row["collector"] == "mcp:imprvhub_mcp_rss_aggregator"


def test_downstream_item_keeps_official_source_from_item() -> None:
    item = NewsItem(
        id="abc",
        title="Title",
        url="https://example.com/a",
        feed_url="https://example.com/rss.xml",
        fetched_at=datetime.now(UTC),
        content_level="summary_only",
        fetch_status="rss_only",
        official_source=True,
    )

    row = _model_item_for_downstream(item, {"https://example.com/rss.xml": {"official_source": False}})

    assert row["official_source"] is True


def test_downstream_item_falls_back_to_active_feed_official_source() -> None:
    item = NewsItem(
        id="abc",
        title="Title",
        url="https://example.com/a",
        feed_url="https://example.com/rss.xml",
        fetched_at=datetime.now(UTC),
        content_level="summary_only",
        fetch_status="rss_only",
    )

    row = _model_item_for_downstream(item, {"https://example.com/rss.xml": {"official_source": True}})

    assert row["official_source"] is True
