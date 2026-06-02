from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterable
import os

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


def _has_existing_fulltext(item: dict) -> bool:
    text = item.get("fulltext") or item.get("content") or item.get("summary") or ""
    if not str(text).strip():
        return False
    return item.get("fulltext_status") in {"success", "partial"} or bool(item.get("fulltext_source"))


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
            "fulltext_coverage_state": "fulltext" if status == "success" else "summary_only" if status == "partial" else "missing",
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


def fetch_fulltext_candidates(items: Iterable[dict], client=None, chunk_size: int = 32, max_workers: int | None = None) -> list[dict]:
    output: list[dict] = []
    items_list = list(items)
    logging.info("fulltext: starting batch with %d items", len(items_list))

    def _process_chunk(chunk: list[dict]) -> list[dict]:
        rows: list[dict] = []
        for index, item in enumerate(chunk, start=1):
            logging.info("fulltext: item %d/%d id=%s", index, len(chunk), item.get("id") or item.get("article_id"))
            if not item.get("fetch_required", True):
                rows.append(
                    _normalize_fulltext_record(
                        item,
                        item.get("fulltext") or item.get("content") or "",
                        "skipped",
                        "skipped",
                        fetch_reason="fetch_required=false",
                    )
                )
                continue

            if _has_existing_fulltext(item):
                rows.append(
                    _normalize_fulltext_record(
                        item,
                        item.get("fulltext") or item.get("content") or item.get("summary") or "",
                        item.get("fulltext_source") or "skipped",
                        "skipped",
                        fetch_reason="already_has_fulltext",
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
                try:
                    payload = fetch_article_content(url, client=client)
                    extracted = _extract_text_from_payload(payload if isinstance(payload, dict) else {"fulltext": payload})
                    if extracted:
                        fulltext = extracted
                        source = "http_fallback"
                        status = "success" if len(_excerpt(extracted, 1_000_000)) > 0 else "partial"
                        fetch_reason = "http_extracted_fulltext"
                    elif rss_content:
                        fulltext = str(rss_content)
                        source = "rss_feed_content"
                        status = "partial"
                        fetch_reason = "rss_content_only"
                    else:
                        status = "skipped"
                        fetch_reason = "http_extracted_empty"
                except Exception as exc:  # noqa: BLE001
                    fetch_error = f"{type(exc).__name__}: {exc}"
                    logging.warning("fulltext fetch failed for %s: %s", url, fetch_error)
                    if rss_content:
                        fulltext = str(rss_content)
                        source = "rss_feed_content"
                        status = "partial"
                        fetch_reason = "rss_content_only"
                    else:
                        status = "skipped"
                        fetch_reason = "http_fetch_failed"
            else:
                fetch_error = "missing URL"
                fetch_reason = "missing_url"

            rows.append(_normalize_fulltext_record(item, fulltext, source, status, fetch_error, fetch_reason))
        return rows

    chunks = [items_list[i : i + chunk_size] for i in range(0, len(items_list), chunk_size)]
    if len(chunks) <= 1:
        for chunk in chunks:
            output.extend(_process_chunk(chunk))
        return output
    with ThreadPoolExecutor(max_workers=max_workers or min(len(chunks), (os.cpu_count() or 1) + 4)) as executor:
        for rows in executor.map(_process_chunk, chunks):
            output.extend(rows)
    return output


def run_fulltext_fetch(
    input_path: str = "data/news_item_labels.jsonl",
    output_path: str = "data/news_item_fulltext.jsonl",
    chunk_size: int = 32,
    max_workers: int | None = None,
) -> list[dict]:
    items = read_jsonl(input_path)
    client = get_mcp_client()
    try:
        fulltext_rows = fetch_fulltext_candidates(items, client=client, chunk_size=chunk_size, max_workers=max_workers)
    finally:
        close_mcp_client()
    write_jsonl(output_path, fulltext_rows)
    return fulltext_rows
