from __future__ import annotations

from time import sleep
from urllib.parse import urlparse

import requests
import trafilatura

from .models import NewsItem
from .utils import TIMEOUT, USER_AGENT, is_blocked_response, read_jsonl, write_jsonl

MIN_FULL_TEXT = 1500
MIN_PARTIAL_TEXT = 300
PAYWALL_MARKERS = ("subscribe to continue", "subscription required", "already a subscriber", "sign in to continue", "register to continue", "paywall")


def _looks_like_paywall(html: str) -> bool:
    sample = html[:10000].lower()
    return any(marker in sample for marker in PAYWALL_MARKERS)


def extract_full_text(item: NewsItem, retries: int = 2, domain_delay_seconds: float = 0.5) -> NewsItem:
    if item.rss_content and len(item.rss_content) >= MIN_FULL_TEXT:
        return item.model_copy(update={"full_text": item.rss_content, "content_level": "full_text", "fetch_status": "success"})

    last_error_status = None
    for attempt in range(retries + 1):
        if attempt:
            sleep(domain_delay_seconds)
        try:
            response = requests.get(item.url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        except requests.RequestException:
            last_error_status = "http_error"
            continue
        if is_blocked_response(response.status_code, response.text):
            return item.model_copy(update={"fetch_status": "blocked"})
        if _looks_like_paywall(response.text):
            return item.model_copy(update={"fetch_status": "paywall"})
        if response.status_code >= 400:
            return item.model_copy(update={"fetch_status": "http_error"})
        text = trafilatura.extract(response.text, include_comments=False, include_tables=False)
        if text and len(text) >= MIN_FULL_TEXT:
            return item.model_copy(update={"full_text": text, "content_level": "full_text", "fetch_status": "success"})
        if text and len(text) >= MIN_PARTIAL_TEXT:
            return item.model_copy(update={"full_text": text, "content_level": "partial", "fetch_status": "success"})
    return item.model_copy(update={"full_text": None, "content_level": "summary_only", "fetch_status": last_error_status or "parse_failed"})


def enrich_news_items(input_path: str = "data/news_items.jsonl", output_path: str = "data/news_items.enriched.jsonl") -> list[NewsItem]:
    raw_items = [NewsItem(**row) for row in read_jsonl(input_path)]
    enriched: list[NewsItem] = []
    last_domain: str | None = None
    for item in raw_items:
        domain = urlparse(item.url).netloc
        if last_domain == domain:
            sleep(0.5)
        last_domain = domain
        if item.content_level in {"summary_only", "partial"}:
            enriched.append(extract_full_text(item))
        else:
            enriched.append(item)
    write_jsonl(output_path, enriched)
    return enriched
