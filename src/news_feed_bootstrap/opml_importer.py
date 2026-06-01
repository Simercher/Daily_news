from __future__ import annotations

import warnings
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests
from defusedxml import ElementTree as SafeET

from .config import read_yaml, resolve_path
from .dedup import normalize_url
from .models import FeedCandidate, SeedSource
from .utils import TIMEOUT, USER_AGENT, write_json


def _read_opml(path_or_url: str) -> str:
    if path_or_url.startswith(("http://", "https://")):
        response = requests.get(path_or_url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        return response.text
    return resolve_path(path_or_url).read_text(encoding="utf-8")


def import_opml(file_path_or_url: str) -> list[FeedCandidate]:
    xml = _read_opml(file_path_or_url)
    root = SafeET.fromstring(xml)
    candidates: list[FeedCandidate] = []
    for outline in root.findall(".//outline"):
        feed_url = outline.attrib.get("xmlUrl") or outline.attrib.get("xmlurl")
        if not feed_url:
            continue
        title = outline.attrib.get("title") or outline.attrib.get("text")
        candidates.append(
            FeedCandidate(
                publisher=title,
                feed_url=feed_url,
                homepage=outline.attrib.get("htmlUrl"),
                discovered_from=file_path_or_url,
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


def import_seed_lists(config_path: str = "configs/seed_sources.yaml") -> list[FeedCandidate]:
    data = read_yaml(config_path, {"seed_sources": []})
    imported: list[FeedCandidate] = []
    for row in data.get("seed_sources", []):
        seed = SeedSource(**row)
        if seed.type not in {"opml", "text"}:
            warnings.warn(
                f"unsupported_seed_type: {seed.id}; raw OPML/text URL must be confirmed manually",
                stacklevel=2,
            )
            continue
        try:
            candidates = import_opml(seed.url) if seed.type == "opml" else import_text_feed_list(seed.url)
            for candidate in candidates:
                candidate.source_id = seed.id
                candidate.source_name = seed.name
                candidate.priority = seed.priority
                candidate.topics = sorted(set(candidate.topics + seed.topics))
            imported.extend(candidates)
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
