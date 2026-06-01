from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .models import NewsItem

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k not in TRACKING_PARAMS]
    normalized = parsed._replace(fragment="", query=urlencode(query, doseq=True))
    return urlunparse(normalized)


def compute_item_id(url: str | None, title: str | None = None, published_at: object | None = None) -> str:
    basis = normalize_url(url) if url else f"{title or ''}|{published_at or ''}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def deduplicate_items(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    deduped: list[NewsItem] = []
    for item in items:
        key = normalize_url(item.canonical_url or item.url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
