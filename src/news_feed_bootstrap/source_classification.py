from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from .config import read_yaml

DEFAULT_OFFICIAL_SOURCES_PATH = "configs/official_sources.yaml"


def _hostname(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return host or None


@lru_cache(maxsize=8)
def _official_source_config(path: str = DEFAULT_OFFICIAL_SOURCES_PATH) -> tuple[tuple[str, ...], tuple[str, ...]]:
    data = read_yaml(path, {"official_domains": [], "official_title_patterns": []}) or {}
    domains = tuple(
        sorted(
            {
                str(domain).strip().lower().removeprefix("www.")
                for domain in data.get("official_domains", [])
                if str(domain).strip()
            }
        )
    )
    title_patterns = tuple(
        str(pattern).strip().lower()
        for pattern in data.get("official_title_patterns", [])
        if str(pattern).strip()
    )
    return domains, title_patterns


def _domain_matches(host: str, official_domain: str) -> bool:
    return host == official_domain or host.endswith(f".{official_domain}")


def is_official_source(
    *,
    feed_url: str | None = None,
    homepage: str | None = None,
    publisher: str | None = None,
    feed_title: str | None = None,
    config_path: str = DEFAULT_OFFICIAL_SOURCES_PATH,
) -> bool:
    """Return true for reviewed first-party/recognized publisher feeds.

    This is a conservative allowlist signal for downstream cross-source verification.
    Unknown blogs, aggregators, vendor blogs, and community feeds remain false until
    added to `configs/official_sources.yaml`.
    """

    domains, title_patterns = _official_source_config(config_path)
    hosts = [host for host in (_hostname(homepage), _hostname(feed_url)) if host]
    if any(_domain_matches(host, official_domain) for host in hosts for official_domain in domains):
        return True

    title_blob = " ".join(part for part in [publisher, feed_title] if part).lower()
    return bool(title_blob and any(pattern in title_blob for pattern in title_patterns))
