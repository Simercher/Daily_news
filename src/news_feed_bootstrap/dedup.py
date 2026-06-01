from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .models import NewsItem

TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "source",
}
TRACKING_PARAM_PREFIXES = ("utm_",)


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    port = parsed.port
    if port is not None and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        hostname = f"{hostname}:{port}"
    if parsed.username is not None:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo = f"{userinfo}:{parsed.password}"
        hostname = f"{userinfo}@{hostname}"

    path = parsed.path
    if path != "/":
        path = path.rstrip("/")

    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_param(key)
    ]
    query.sort()
    normalized = parsed._replace(
        scheme=scheme,
        netloc=hostname,
        path=path,
        fragment="",
        query=urlencode(query, doseq=True),
    )
    return urlunparse(normalized)


def _is_tracking_param(key: str) -> bool:
    normalized_key = key.lower()
    return normalized_key in TRACKING_PARAMS or normalized_key.startswith(TRACKING_PARAM_PREFIXES)


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
