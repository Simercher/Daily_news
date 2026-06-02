from __future__ import annotations

import re
import warnings
import xml.etree.ElementTree as ET
from html import unescape
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests
from defusedxml import ElementTree as SafeET

from .config import read_yaml, resolve_path
from .dedup import normalize_url
from .models import FeedCandidate, SeedSource
from .utils import TIMEOUT, USER_AGENT, write_json

_SOURCE_TIER_BY_TRUST = {
    "primary": "tier1",
    "major_media": "tier1",
    "specialist": "tier2",
    "aggregator": "tier3",
    "third_party_generated": "tier3",
    "unknown": "unknown",
}

_SOURCE_ROLE_BY_TRUST = {
    "primary": "official",
    "major_media": "major_media",
    "specialist": "specialist",
    "aggregator": "aggregator",
    "third_party_generated": "community",
    "unknown": "unknown",
}

_SOURCE_FORMAT_BY_TYPE = {
    "rss": "rss",
    "google_news_rss": "google_news_rss",
    "generated_rss": "generated_rss",
    "opml": "opml",
    "text": "text",
    "html_feed_index": "html_feed_index",
    "feed_discovery": "html_feed_index",
    "github_page": "unknown",
    "web_directory": "unknown",
}


def _source_tier_from_trust_tier(trust_tier: str | None) -> str:
    return _SOURCE_TIER_BY_TRUST.get(trust_tier or "unknown", "unknown")


def _source_role_from_trust_tier(trust_tier: str | None) -> str:
    return _SOURCE_ROLE_BY_TRUST.get(trust_tier or "unknown", "unknown")


def _source_format_from_seed_type(seed_type: str) -> str:
    return _SOURCE_FORMAT_BY_TYPE.get(seed_type, "unknown")


def _read_opml(path_or_url: str) -> str:
    if path_or_url.startswith(("http://", "https://")):
        response = requests.get(path_or_url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        return response.text
    return resolve_path(path_or_url).read_text(encoding="utf-8")


def _outline_attrs_from_xml(xml: str) -> list[dict[str, str]]:
    try:
        root = SafeET.fromstring(xml)
    except ET.ParseError:
        return _outline_attrs_from_tolerant_regex(xml)
    return [dict(outline.attrib) for outline in root.findall(".//outline")]


def _outline_attrs_from_tolerant_regex(xml: str) -> list[dict[str, str]]:
    outlines: list[dict[str, str]] = []
    for match in re.finditer(r"<outline\b(?P<attrs>[^>]*)>", xml, flags=re.IGNORECASE):
        attrs_text = match.group("attrs")
        attrs = {
            attr_match.group("key"): unescape(attr_match.group("value"))
            for attr_match in re.finditer(
                r"(?P<key>[A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
                attrs_text,
                flags=re.DOTALL,
            )
        }
        if attrs:
            outlines.append(attrs)
    return outlines


def _outline_path_topics(attrs: dict[str, str]) -> list[str]:
    category = attrs.get("category") or attrs.get("tags")
    if not category:
        return []
    return [part.strip().lower().replace(" ", "_") for part in re.split(r"[,/|]", category) if part.strip()]


def import_opml(file_path_or_url: str) -> list[FeedCandidate]:
    xml = _read_opml(file_path_or_url)
    candidates: list[FeedCandidate] = []
    for attrs in _outline_attrs_from_xml(xml):
        feed_url = attrs.get("xmlUrl") or attrs.get("xmlurl")
        if not feed_url:
            continue
        title = attrs.get("title") or attrs.get("text")
        candidates.append(
            FeedCandidate(
                publisher=title,
                feed_url=feed_url,
                homepage=attrs.get("htmlUrl"),
                discovered_from=file_path_or_url,
                topics=_outline_path_topics(attrs),
            )
        )
    return candidates


def import_direct_feed(url: str, *, collector: str = "local_feedparser") -> list[FeedCandidate]:
    parsed = urlparse(url)
    publisher = parsed.netloc.removeprefix("www.") if parsed.netloc else None
    return [FeedCandidate(publisher=publisher, feed_url=url, discovered_from=url, collector=collector)]


def discover_feeds_from_html(url: str) -> list[FeedCandidate]:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    candidates: list[FeedCandidate] = []
    seen: set[str] = set()

    for link in soup.find_all("link"):
        raw_rel = link.get("rel") or []
        rel_values = raw_rel if isinstance(raw_rel, list) else str(raw_rel).split()
        rel = {str(part).lower() for part in rel_values}
        mime_type = str(link.get("type") or "").lower()
        href = link.get("href")
        if "alternate" not in rel or not href:
            continue
        if mime_type not in {"application/rss+xml", "application/atom+xml", "application/rdf+xml"}:
            continue
        feed_url = urljoin(url, href)
        if feed_url in seen:
            continue
        seen.add(feed_url)
        candidates.append(
            FeedCandidate(
                publisher=link.get("title"),
                feed_url=feed_url,
                homepage=url,
                discovered_from=url,
            )
        )

    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not href:
            continue
        text_blob = " ".join(str(part) for part in [anchor.get_text(" ", strip=True), href]).lower()
        if not any(marker in text_blob for marker in ("rss", "atom", ".xml", "/feed")):
            continue
        feed_url = urljoin(url, href)
        if feed_url in seen:
            continue
        seen.add(feed_url)
        candidates.append(
            FeedCandidate(
                publisher=anchor.get_text(" ", strip=True) or None,
                feed_url=feed_url,
                homepage=url,
                discovered_from=url,
            )
        )
    return candidates


def import_text_feed_list(file_path_or_url: str) -> list[FeedCandidate]:
    text = _read_opml(file_path_or_url)
    candidates: list[FeedCandidate] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        feed_url = next((part for part in parts if part.startswith(("http://", "https://"))), None)
        if not feed_url:
            continue
        parsed = urlparse(feed_url)
        candidates.append(
            FeedCandidate(
                publisher=parsed.netloc.removeprefix("www."),
                feed_url=feed_url,
                discovered_from=file_path_or_url,
            )
        )
    return candidates


def merge_discovered(candidates: list[FeedCandidate], path: str = "data/imported_feeds.json") -> list[FeedCandidate]:
    existing = [FeedCandidate(**row) for row in (read_yaml(path, {"feeds": []}).get("feeds") or [])]
    by_url = {normalize_url(item.feed_url): item for item in existing}
    for candidate in candidates:
        by_url.setdefault(normalize_url(candidate.feed_url), candidate)
    merged = list(by_url.values())
    write_json(path, {"feeds": [c.model_dump(mode="json") for c in merged]})
    return merged


def _apply_seed_metadata(candidate: FeedCandidate, seed: SeedSource) -> FeedCandidate:
    candidate.source_id = seed.id
    candidate.source_name = seed.name
    candidate.priority = seed.priority
    candidate.trust_tier = seed.trust_tier
    candidate.source_tier = seed.source_tier or _source_tier_from_trust_tier(seed.trust_tier)
    candidate.source_role = seed.source_role or _source_role_from_trust_tier(seed.trust_tier)
    candidate.source_format = seed.source_format or _source_format_from_seed_type(seed.type)
    candidate.language = candidate.language or seed.language
    candidate.region = candidate.region or seed.region
    candidate.dedupe_group = seed.dedupe_group
    candidate.commercial_use_risk = seed.commercial_use_risk
    if seed.type == "google_news_rss":
        candidate.collector = "google_news_rss"
    elif seed.type == "generated_rss":
        candidate.collector = "generated_rss"
    candidate.topics = sorted(set(candidate.topics + seed.topics))
    return candidate


def import_seed_lists(config_path: str = "configs/seed_sources.yaml") -> list[FeedCandidate]:
    data = read_yaml(config_path, {"seed_sources": []})
    imported: list[FeedCandidate] = []
    for row in data.get("seed_sources", []):
        seed = SeedSource(**row)
        if not seed.enabled:
            continue
        if seed.type in {"github_page", "web_directory"}:
            warnings.warn(
                f"unsupported_seed_type: {seed.id}; raw OPML/text URL must be confirmed manually",
                stacklevel=2,
            )
            continue
        try:
            if seed.type == "opml":
                candidates = import_opml(seed.url)
            elif seed.type == "text":
                candidates = import_text_feed_list(seed.url)
            elif seed.type in {"rss", "google_news_rss", "generated_rss"}:
                candidates = import_direct_feed(seed.url)
            elif seed.type in {"html_feed_index", "feed_discovery"}:
                candidates = discover_feeds_from_html(seed.url)
                if not candidates:
                    warnings.warn(f"feed_not_found: {seed.id}: {seed.url}", stacklevel=2)
            else:
                candidates = []
            for candidate in candidates:
                _apply_seed_metadata(candidate, seed)
                imported.append(candidate)
        except Exception as exc:  # noqa: BLE001 - keep batch import moving.
            warnings.warn(f"failed_seed_import: {seed.id}: {exc}", stacklevel=2)
    return merge_discovered(imported)


def write_feeds_opml(feeds: list[dict], output_path: str, title: str) -> None:
    opml = ET.Element("opml", version="2.0")
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = title
    body = ET.SubElement(opml, "body")
    for feed in feeds:
        title = feed.get("publisher") or feed.get("feed_title") or feed["feed_url"]
        attrs = {"text": title, "title": title, "type": "rss", "xmlUrl": feed["feed_url"]}
        if feed.get("homepage"):
            attrs["htmlUrl"] = feed["homepage"]
        ET.SubElement(body, "outline", attrs)
    target = resolve_path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(opml).write(target, encoding="utf-8", xml_declaration=True)


def write_active_opml(feeds: list[dict], output_path: str = "data/active_feeds.opml") -> None:
    write_feeds_opml(feeds, output_path, "Daily News Active Feeds")
