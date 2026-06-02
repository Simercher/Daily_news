from __future__ import annotations

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


def test_extract_markdown_from_html_uses_bbc_text_block() -> None:
    html = """
    <html><head><title>BBC Title</title></head>
    <body>
      <div data-component="text-block"><div><p>BBC first</p><p>BBC second</p></div></div>
    </body></html>
    """
    payload = mcp_fetcher._extract_markdown_from_html(html, "https://www.bbc.com/news/articles/abc")
    assert payload["title"] == "BBC Title"
    assert "BBC first" in payload["content"]
    assert "BBC second" in payload["content"]


def test_extract_markdown_from_html_uses_independent_selector() -> None:
    html = """
    <html><head><title>Independent Title</title></head>
    <body>
      <div class="sc-14x1gfp-0 fCHrkm sc-14x1gfp-1"><div><p>Indie first</p><p>Indie second</p></div></div>
    </body></html>
    """
    payload = mcp_fetcher._extract_markdown_from_html(html, "https://www.independent.co.uk/news/article")
    assert payload["title"] == "Independent Title"
    assert "Indie first" in payload["content"]
    assert "Indie second" in payload["content"]


def test_extract_markdown_from_html_uses_quartz_selector() -> None:
    html = """
    <html><head><title>Quartz Title</title></head>
    <body>
      <div class="payload-richtext prose md:prose-md dark:prose-invert"><p>Quartz first</p><p>Quartz second</p></div>
    </body></html>
    """
    payload = mcp_fetcher._extract_markdown_from_html(html, "https://qz.com/article")
    assert payload["title"] == "Quartz Title"
    assert "Quartz first" in payload["content"]
    assert "Quartz second" in payload["content"]


def test_extract_markdown_from_html_uses_cnbc_selector() -> None:
    html = """
    <html><head><title>CNBC Title</title></head>
    <body>
      <div class="ArticleBody-articleBody"><p>CNBC first</p><p>CNBC second</p></div>
    </body></html>
    """
    payload = mcp_fetcher._extract_markdown_from_html(html, "https://www.cnbc.com/article")
    assert payload["title"] == "CNBC Title"
    assert "CNBC first" in payload["content"]
    assert "CNBC second" in payload["content"]


def test_fetch_article_content_uses_url_specific_extractor(monkeypatch) -> None:
    html = "<html><head><title>BBC Title</title></head><body><div data-component='text-block'><p>BBC body</p></div></body></html>"
    fake = FakeSession(FakeResponse(html))
    monkeypatch.setattr(mcp_fetcher, "_HTTP_CLIENT", mcp_fetcher._HTTPArticleClient(session=fake))  # type: ignore[arg-type]
    payload = mcp_fetcher.fetch_article_content("https://www.bbc.com/news/articles/abc")
    assert "BBC body" in payload["fulltext"]
    mcp_fetcher.close_mcp_client()
