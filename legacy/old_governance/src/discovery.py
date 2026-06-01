from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .config import DATA_DIR, read_yaml, write_yaml
from .models import FeedCandidate, Publisher
from .utils import TIMEOUT, USER_AGENT

COMMON_PATHS = ("/rss", "/rss.xml", "/feed", "/feed.xml", "/feeds", "/atom.xml", "/news/rss", "/world/rss")
FEED_TYPES = {"application/rss+xml", "application/atom+xml", "application/xml", "text/xml"}


def _candidate(url: str, homepage: str | None, discovered_from: str, publisher: Publisher | None = None) -> FeedCandidate:
    return FeedCandidate(
        publisher=publisher.name if publisher else None,
        feed_url=url,
        homepage=homepage,
        discovered_from=discovered_from,
        official=publisher.official if publisher else None,
        publisher_type=publisher.type if publisher else None,
        region=publisher.region if publisher else None,
        language=publisher.language if publisher else None,
        topics=publisher.topics if publisher else [],
        priority=publisher.priority if publisher else None,
    )


def _looks_like_feed(text: str, content_type: str = "") -> bool:
    sample = text[:500].lower()
    return "rss" in sample or "<feed" in sample or "atom" in sample or any(kind in content_type.lower() for kind in FEED_TYPES)


def discover_from_homepage(homepage_url: str) -> list[FeedCandidate]:
    response = requests.get(homepage_url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    candidates: list[FeedCandidate] = []
    for link in soup.find_all("link", rel=lambda value: value and "alternate" in value):
        content_type = (link.get("type") or "").lower()
        href = link.get("href")
        if href and content_type in {"application/rss+xml", "application/atom+xml"}:
            candidates.append(_candidate(urljoin(homepage_url, href), homepage_url, "homepage_alternate_link"))
    return candidates


def discover_common_paths(homepage_url: str) -> list[FeedCandidate]:
    parsed = urlparse(homepage_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    candidates: list[FeedCandidate] = []
    for path in COMMON_PATHS:
        url = urljoin(base, path)
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        except requests.RequestException:
            continue
        if response.status_code == 200 and _looks_like_feed(response.text, response.headers.get("content-type", "")):
            candidates.append(_candidate(url, homepage_url, "common_path"))
    return candidates


def discover_from_publishers(config_path: str = "configs/candidate_publishers.yaml") -> list[FeedCandidate]:
    data = read_yaml(config_path, {"publishers": []})
    discovered: list[FeedCandidate] = []
    seen: set[str] = set()
    for row in data.get("publishers", []):
        publisher = Publisher(**row)
        for discoverer in (discover_from_homepage, discover_common_paths):
            try:
                candidates = discoverer(publisher.homepage)
            except requests.RequestException:
                continue
            for candidate in candidates:
                if candidate.feed_url in seen:
                    continue
                seen.add(candidate.feed_url)
                discovered.append(candidate.model_copy(update={
                    "publisher": publisher.name,
                    "official": publisher.official,
                    "publisher_type": publisher.type,
                    "region": publisher.region,
                    "language": publisher.language,
                    "topics": publisher.topics,
                    "priority": publisher.priority,
                }))
    write_yaml(DATA_DIR / "discovered_feeds.yaml", {"feeds": [c.model_dump(mode="json") for c in discovered]})
    return discovered
