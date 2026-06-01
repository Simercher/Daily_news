from __future__ import annotations

from datetime import UTC, datetime

from news_feed_bootstrap.classifier import run_article_classifier
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


def test_downstream_item_preserves_url_fields_for_fulltext_fetch() -> None:
    item = NewsItem(
        id="abc",
        title="Title",
        url="https://example.com/a?utm_source=x",
        canonical_url="https://example.com/a",
        feed_url="https://example.com/rss.xml",
        fetched_at=datetime.now(UTC),
        content_level="summary_only",
        fetch_status="rss_only",
    )

    row = _model_item_for_downstream(item, {"https://example.com/rss.xml": {}})

    assert row["url"] == "https://example.com/a?utm_source=x"
    assert row["canonical_url"] == "https://example.com/a"
    assert row["feed_url"] == "https://example.com/rss.xml"


def test_run_article_classifier_preserves_manifest_urls(tmp_path, monkeypatch) -> None:
    input_path = tmp_path / "deduped.jsonl"
    output_path = tmp_path / "labels.jsonl"
    input_path.write_text(
        '{"id":"1","title":"Example","url":"https://example.com/article?utm_source=x","canonical_url":"https://example.com/article","feed_url":"https://example.com/feed.xml","fetched_at":"2026-01-01T00:00:00Z","collector":"local_feedparser","official_source":true}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "news_feed_bootstrap.classifier.classify_articles",
        lambda items: [{"article_id": "1", "primary_domain": "technology"}],
    )

    rows = run_article_classifier(str(input_path), str(output_path), cluster_threshold=1.0)

    assert rows[0]["url"] == "https://example.com/article?utm_source=x"
    assert rows[0]["canonical_url"] == "https://example.com/article"
    assert rows[0]["feed_url"] == "https://example.com/feed.xml"
    assert rows[0]["article_id"] == "1"
    assert output_path.exists()
