from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import requests
from bs4 import BeautifulSoup

from .utils import TIMEOUT, USER_AGENT, is_blocked_response

FETCH_TIMEOUT_SECONDS = 20
PAYWALL_MARKERS = (
    "subscribe to continue",
    "subscription required",
    "already a subscriber",
    "sign in to continue",
    "register to continue",
    "paywall",
)


@dataclass
class MCPTransportError(RuntimeError):
    message: str


@dataclass
class _HTTPArticleClient:
    session: requests.Session

    def close(self) -> None:
        self.session.close()


_HTTP_CLIENT: _HTTPArticleClient | None = None


def _get_http_client() -> _HTTPArticleClient:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        _HTTP_CLIENT = _HTTPArticleClient(session=session)
    return _HTTP_CLIENT


def close_mcp_client() -> None:
    global _HTTP_CLIENT
    client = _HTTP_CLIENT
    _HTTP_CLIENT = None
    if client is not None:
        client.close()


def default_mcp_server_command() -> list[str]:
    return []


def mcp_server_ready() -> bool:
    return False


def get_mcp_client() -> _HTTPArticleClient:
    return _get_http_client()


def _looks_like_paywall(html: str) -> bool:
    sample = html[:10000].lower()
    return any(marker in sample for marker in PAYWALL_MARKERS)


def _extract_markdown_from_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()

    title = "Untitled Article"
    if soup.title and soup.title.text.strip():
        title = soup.title.text.strip()
    elif soup.h1 and soup.h1.text.strip():
        title = soup.h1.text.strip()

    candidates = [
        soup.find("article"),
        soup.find(attrs={"role": "main"}),
        soup.find("main"),
        soup.find(class_=re.compile(r"(content|post-content|entry-content|article-content)", re.I)),
    ]
    content_root = next((node for node in candidates if node is not None), None)
    if content_root is None:
        paragraphs = soup.find_all("p")
        content_root = max((p.parent for p in paragraphs if p.parent), key=lambda el: len(el.get_text(" ", strip=True)), default=soup.body or soup)

    blocks: list[str] = []
    for node in content_root.find_all(["p", "h1", "h2", "h3", "h4", "li", "blockquote", "pre"], recursive=True):
        text = node.get_text(" ", strip=True)
        if text:
            blocks.append(text)
    if not blocks:
        text = content_root.get_text(" ", strip=True)
        blocks = [text] if text else []

    content = "\n\n".join(blocks).strip()
    return {"title": title, "content": content}


def fetch_article_content(url: str, client: _HTTPArticleClient | None = None) -> dict[str, Any]:
    client = client or get_mcp_client()
    logging.info("fulltext: fetching url=%s", url)
    response = client.session.get(url, timeout=FETCH_TIMEOUT_SECONDS, allow_redirects=True)
    if is_blocked_response(response.status_code, response.text):
        raise MCPTransportError(f"blocked response HTTP {response.status_code}")
    if response.status_code >= 400:
        raise MCPTransportError(f"HTTP {response.status_code} {response.reason}")
    html = response.text
    if _looks_like_paywall(html):
        raise MCPTransportError("paywall detected")
    extracted = _extract_markdown_from_html(html)
    extracted.update({"url": url, "extractedAt": ""})
    return {"fulltext": extracted.get("content", ""), "title": extracted.get("title", "Untitled Article"), "url": url, "extractedAt": ""}


def fetch_feed_entries(url: str, limit: int = 10, client: _HTTPArticleClient | None = None) -> dict[str, Any]:
    _ = client
    raise MCPTransportError("fetch_feed_entries is not supported in HTTP fallback mode")


def run_mcp_latest_query(opml_path: str, since_hours: int = 24, limit: int | None = None) -> list[dict]:
    _ = (opml_path, since_hours, limit)
    return []


def mcp_healthcheck(url: str | None = None) -> dict[str, Any]:
    started = __import__("time").monotonic()
    client = get_mcp_client()
    startup_seconds = __import__("time").monotonic() - started
    result: dict[str, Any] = {"ok": True, "startup_seconds": round(startup_seconds, 2), "mode": "http_fallback"}
    if url:
        fetched_started = __import__("time").monotonic()
        payload = fetch_article_content(url, client=client)
        result.update(
            {
                "url": url,
                "fetch_seconds": round(__import__("time").monotonic() - fetched_started, 2),
                "keys": list(payload.keys())[:20] if isinstance(payload, dict) else [],
                "payload_type": type(payload).__name__,
            }
        )
    return result
