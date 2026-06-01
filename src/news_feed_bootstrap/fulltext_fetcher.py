from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from .mcp_fetcher import close_mcp_client, fetch_article_content, get_mcp_client
from .utils import read_jsonl, utc_now, write_jsonl

FULLTEXT_SCHEMA_VERSION = "news_item_fulltext.v1"


@dataclass(frozen=True)
class FulltextFetchResult:
    row: dict


def _now_iso() -> str:
    return utc_now().isoformat()


def _word_count(text: str | None) -> int:
    if not text:
        return 0
    return len([token for token in text.split() if token.strip()])


def _excerpt(text: str | None, limit: int = 280) -> str:
    if not text:
        return ""
    compact = " ".join(text.split())
    return compact[:limit]


def _best_url(item: dict) -> str:
    return item.get("canonical_url") or item.get("url") or item.get("feed_url") or ""


def _language_guess(item: dict) -> str | None:
    return item.get("language") or None


def _normalize_fulltext_record(
    item: dict,
    fulltext: str | None,
    source: str,
    status: str,
    fetch_error: str | None = None,
    fetch_reason: str | None = None,
) -> dict:
    text = fulltext or ""
    row = dict(item)
    row.update(
        {
            "schema_version": FULLTEXT_SCHEMA_VERSION,
            "fulltext": text,
            "fulltext_source": source,
            "fulltext_fetched_at": _now_iso(),
            "fulltext_status": status,
            "fulltext_word_count": _word_count(text),
            "fulltext_language": _language_guess(item),
            "fulltext_excerpt": _excerpt(text),
            "fetch_attempted": True,
            "fetch_error": fetch_error,
            "fetch_reason": fetch_reason,
        }
    )
    return row


def _extract_text_from_payload(payload: dict) -> str:
    for key in ("fulltext", "content", "text", "body", "article_text", "rss_content", "summary"):
        value = payload.get(key)
        if value:
            return str(value)
    return ""


def fetch_fulltext_candidates(items: Iterable[dict], client=None) -> list[dict]:
    output: list[dict] = []
    items_list = list(items)
    logging.info("fulltext: starting batch with %d items", len(items_list))
    for index, item in enumerate(items_list, start=1):
        logging.info("fulltext: item %d/%d id=%s", index, len(items_list), item.get("id") or item.get("article_id"))
        if not item.get("fetch_required", True):
            output.append(
                _normalize_fulltext_record(
                    item,
                    item.get("fulltext") or item.get("content") or "",
                    "skipped",
                    "skipped",
                    fetch_reason="fetch_required=false",
                )
            )
            continue

        url = _best_url(item)
        fetch_error: str | None = None
        fetch_reason: str | None = None
        fulltext = ""
        source = "unknown"
        status = "failed"

        if url:
            rss_content = item.get("content") or item.get("summary") or ""
            if rss_content:
                fulltext = str(rss_content)
                source = "rss_feed_content"
                status = "partial"
                fetch_reason = "rss_content_only"
            try:
                payload = fetch_article_content(url, client=client)
                extracted = _extract_text_from_payload(payload if isinstance(payload, dict) else {"fulltext": payload})
                if extracted:
                    fulltext = extracted
                    source = "http_fallback" if source == "unknown" else source
                    status = "success" if len(_excerpt(extracted, 1_000_000)) > 0 else "partial"
                    fetch_reason = "http_extracted_fulltext"
                elif fulltext:
                    status = "partial"
                    fetch_reason = fetch_reason or "http_extracted_empty_using_rss_content"
                else:
                    status = "skipped"
                    fetch_reason = "http_extracted_empty"
            except Exception as exc:  # noqa: BLE001
                fetch_error = f"{type(exc).__name__}: {exc}"
                logging.warning("fulltext fetch failed for %s: %s", url, fetch_error)
                if fulltext:
                    status = "partial"
                    fetch_reason = fetch_reason or "http_fetch_failed_using_rss_content"
                else:
                    status = "skipped"
                    fetch_reason = "http_fetch_failed"
        else:
            fetch_error = "missing URL"
            fetch_reason = "missing_url"

        output.append(_normalize_fulltext_record(item, fulltext, source, status, fetch_error, fetch_reason))
    return output


def run_fulltext_fetch(
    input_path: str = "data/news_item_labels.jsonl",
    output_path: str = "data/news_item_fulltext.jsonl",
) -> list[dict]:
    items = read_jsonl(input_path)
    client = get_mcp_client()
    try:
        fulltext_rows = fetch_fulltext_candidates(items, client=client)
    finally:
        close_mcp_client()
    write_jsonl(output_path, fulltext_rows)
    return fulltext_rows
