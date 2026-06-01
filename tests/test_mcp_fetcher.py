from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

import news_feed_bootstrap.mcp_fetcher as mcp_fetcher


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200, reason: str = "OK") -> None:
        self.text = text
        self.status_code = status_code
        self.reason = reason


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.headers = {}
        self.closed = False
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return self.response

    def close(self) -> None:
        self.closed = True


def test_fetch_article_content_extracts_markdown_from_html(monkeypatch) -> None:
    html = """
    <html><head><title>Hello Title</title></head>
    <body><article><p>First para.</p><p>Second para.</p></article></body></html>
    """
    fake = FakeSession(FakeResponse(html))
    monkeypatch.setattr(mcp_fetcher, "_HTTP_CLIENT", mcp_fetcher._HTTPArticleClient(session=fake))  # type: ignore[arg-type]

    payload = mcp_fetcher.fetch_article_content("https://example.com/article")

    assert payload["title"] == "Hello Title"
    assert "First para." in payload["fulltext"]
    assert "Second para." in payload["fulltext"]
    assert fake.calls[0][0] == "https://example.com/article"
    mcp_fetcher.close_mcp_client()
    assert fake.closed is True


def test_healthcheck_reports_http_mode(monkeypatch) -> None:
    html = "<html><head><title>T</title></head><body><article><p>X</p></article></body></html>"
    fake = FakeSession(FakeResponse(html))
    monkeypatch.setattr(mcp_fetcher, "_HTTP_CLIENT", mcp_fetcher._HTTPArticleClient(session=fake))  # type: ignore[arg-type]

    result = mcp_fetcher.mcp_healthcheck("https://example.com/article")

    assert result["ok"] is True
    assert result["mode"] == "http_fallback"
    assert result["url"] == "https://example.com/article"
    mcp_fetcher.close_mcp_client()
