from __future__ import annotations

from datetime import datetime, timezone

import requests

from news_rss_pipeline.article_extractor import extract_full_text
from news_rss_pipeline.models import NewsItem


class FakePaywallResponse:
    status_code = 200
    text = "Subscribe to continue reading this article."


def test_extract_full_text_marks_paywall(monkeypatch) -> None:
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakePaywallResponse())
    item = NewsItem(
        id="abc",
        title="Title",
        url="https://example.com/article",
        feed_url="https://example.com/rss.xml",
        fetched_at=datetime.now(timezone.utc),
        content_level="summary_only",
        fetch_status="rss_only",
    )

    enriched = extract_full_text(item)

    assert enriched.fetch_status == "paywall"
