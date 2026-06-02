from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
from typing import Iterable
import os

from .utils import read_jsonl, write_jsonl

DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "ai": (
        "ai",
        "artificial intelligence",
        "llm",
        "large language model",
        "genai",
        "generative ai",
        "openai",
        "anthropic",
        "gemini",
        "copilot",
        "chatgpt",
        "claude",
        "mistral",
        "deepseek",
        "model",
        "inference",
        "prompt",
    ),
    "technology": (
        "software",
        "product",
        "platform",
        "developer",
        "api",
        "cloud",
        "chip",
        "semiconductor",
        "startup",
        "technology",
        "tech",
        "microsoft",
        "google",
        "apple",
        "meta",
        "nvidia",
    ),
    "business": (
        "company",
        "market",
        "ceo",
        "revenue",
        "funding",
        "acquisition",
        "investor",
        "earnings",
        "merger",
        "sale",
        "business",
    ),
    "finance": (
        "stocks",
        "stock",
        "bond",
        "rates",
        "fed",
        "inflation",
        "bank",
        "financial",
        "finance",
        "trading",
        "market",
    ),
    "security": (
        "security",
        "breach",
        "vulnerability",
        "hack",
        "malware",
        "ransomware",
        "cyber",
        "exploit",
    ),
    "politics": ("election", "president", "congress", "parliament", "minister", "policy", "politics"),
    "world": ("war", "ukraine", "gaza", "china", "taiwan", "russia", "israel", "global", "international"),
    "science": ("research", "study", "scientists", "science", "laboratory", "paper"),
    "health": ("health", "medical", "hospital", "drug", "clinic", "disease", "medicine"),
    "climate": ("climate", "carbon", "emissions", "energy", "renewable", "weather", "environment"),
    "culture": ("music", "film", "movie", "art", "culture", "books", "tv", "game"),
    "media": ("media", "journalism", "press", "broadcast", "podcast", "newsletter"),
    "law": ("court", "law", "legal", "judge", "lawsuit", "regulation", "regulatory"),
    "sports": ("sport", "game", "match", "league", "team", "tournament"),
    "local": ("city", "county", "local", "state", "municipal", "community"),
}

DOMAIN_PRIORITY = [
    "ai",
    "security",
    "finance",
    "business",
    "technology",
    "world",
    "politics",
    "science",
    "health",
    "climate",
    "law",
    "media",
    "culture",
    "sports",
    "local",
    "other",
]

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "generative_ai": ("generative ai", "genai", "llm", "openai", "claude", "chatgpt", "copilot"),
    "enterprise_software": ("enterprise", "saas", "workflow", "platform", "software"),
    "cybersecurity": ("security", "cyber", "breach", "ransomware", "malware", "vulnerability"),
    "semiconductors": ("chip", "semiconductor", "gpu", "nvidia", "tsmc"),
    "macroeconomics": ("inflation", "rates", "fed", "gdp", "economy", "recession"),
    "capital_markets": ("stocks", "bond", "ipo", "earnings", "trading", "market"),
    "policy": ("policy", "regulation", "regulatory", "government", "law"),
    "healthcare": ("health", "medical", "drug", "hospital", "medicine", "pharma"),
    "climate_policy": ("climate", "emissions", "carbon", "renewable", "energy"),
}

ENTITY_RE = re.compile(r"\b(?:[A-Z][\w&.-]+(?:\s+[A-Z][\w&.-]+){0,3})\b")


@dataclass(frozen=True)
class ClassificationResult:
    row: dict
    skipped: bool = False


def _text_fields(item: dict) -> str:
    parts: list[str] = []
    for key in ("title", "summary", "content", "feed_title", "feed_url", "category", "source_seed_name", "published_at"):
        value = item.get(key)
        if value:
            parts.append(str(value))
    return " \n".join(parts).strip().lower()


def _pick_domain(text: str) -> tuple[str, float]:
    scores = Counter()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                scores[domain] += 1
    if not scores:
        return "other", 0.35
    domain, score = max(scores.items(), key=lambda kv: (kv[1], -DOMAIN_PRIORITY.index(kv[0]) if kv[0] in DOMAIN_PRIORITY else 0))
    confidence = min(0.97, 0.45 + 0.12 * score)
    return domain, confidence


def _secondary_domains(primary: str, text: str) -> list[str]:
    scores = []
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if domain == primary:
            continue
        hits = sum(1 for kw in keywords if kw in text)
        if hits:
            scores.append((hits, domain))
    scores.sort(key=lambda x: (-x[0], DOMAIN_PRIORITY.index(x[1]) if x[1] in DOMAIN_PRIORITY else 999))
    return [domain for _, domain in scores[:2]]


def _topics(text: str, primary: str) -> list[str]:
    topics = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            topics.append(topic)
    if not topics and primary != "other":
        topics.append(primary)
    return topics[:5]


def _entities(item: dict) -> list[str]:
    fields = " ".join(str(item.get(key) or "") for key in ("title", "summary", "content", "feed_title"))
    seen = []
    for match in ENTITY_RE.findall(fields):
        candidate = match.strip()
        if len(candidate) < 2:
            continue
        if candidate not in seen:
            seen.append(candidate)
    return seen[:10]


def _content_type(text: str) -> str:
    if any(word in text for word in ("analysis", "deep dive", "explainer")):
        return "analysis"
    if any(word in text for word in ("interview", "q&a", "qa")):
        return "interview"
    if any(word in text for word in ("opinion", "editorial", "commentary")):
        return "opinion"
    if any(word in text for word in ("press release", "announcement", "introducing", "launch")):
        return "press_release"
    if any(word in text for word in ("live", "breaking", "update")):
        return "live_update"
    return "news"


def _geography(text: str) -> list[str]:
    places = []
    for place in ("United States", "China", "Taiwan", "United Kingdom", "Europe", "Japan", "Germany", "France", "India", "Canada"):
        if place.lower() in text:
            places.append(place)
    return places[:4]


TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
TITLE_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _normalize_title(title: str) -> str:
    tokens = [token.lower() for token in TITLE_WORD_RE.findall(title)]
    filtered = [token for token in tokens if token not in TITLE_STOPWORDS]
    return " ".join(filtered)


def _title_similarity(first: str, second: str) -> float:
    if not first or not second:
        return 0.0
    first_norm = _normalize_title(first)
    second_norm = _normalize_title(second)
    if not first_norm or not second_norm:
        return 0.0
    return SequenceMatcher(None, first_norm, second_norm).ratio()


def cluster_title_similar_items(items: list[dict], threshold: float = 0.86) -> list[dict]:
    if not items:
        return []
    parent = list(range(len(items)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i, j in combinations(range(len(items)), 2):
        if _title_similarity(items[i].get("title", ""), items[j].get("title", "")) >= threshold:
            union(i, j)

    clusters: dict[int, list[int]] = {}
    for idx in range(len(items)):
        root = find(idx)
        clusters.setdefault(root, []).append(idx)

    enriched: list[dict] = []
    for cluster_index, member_indexes in enumerate(sorted(clusters.values(), key=lambda xs: xs[0])):
        member_indexes = sorted(member_indexes)
        representative_index = member_indexes[0]
        representative_id = items[representative_index]["id"]
        cluster_id = f"title_cluster_{cluster_index:05d}"
        for position, item_index in enumerate(member_indexes):
            item = dict(items[item_index])
            item["title_cluster_id"] = cluster_id
            item["title_cluster_size"] = len(member_indexes)
            item["title_cluster_rank"] = position + 1
            item["title_cluster_primary_id"] = representative_id
            item["title_cluster_is_primary"] = item["id"] == representative_id
            enriched.append(item)
    return enriched


def classify_item(item: dict) -> ClassificationResult:
    text = _text_fields(item)
    primary_domain, confidence = _pick_domain(text)
    secondary_domains = _secondary_domains(primary_domain, text)
    topics = _topics(text, primary_domain)
    entities = _entities(item)
    needs_human_review = confidence < 0.6 or primary_domain == "other"
    same_event_cluster_id = item.get("title_cluster_id") or item.get("same_event_cluster_id")
    same_event_cluster_primary_id = item.get("title_cluster_primary_id") or item.get("same_event_cluster_primary_id")
    same_event_cluster_rank = item.get("title_cluster_rank") or item.get("same_event_cluster_rank")
    same_event_cluster_size = item.get("title_cluster_size") or item.get("same_event_cluster_size")
    fetch_priority = round(min(1.0, 0.45 + confidence * 0.45 + (0.1 if needs_human_review else 0.0)), 2)
    skip_fulltext = False
    row = {
        "schema_version": "news_item_enriched.v1",
        "article_id": item["id"],
        "title": item.get("title"),
        "url": item.get("url"),
        "canonical_url": item.get("canonical_url") or item.get("url"),
        "feed_url": item.get("feed_url"),
        "feed_title": item.get("feed_title"),
        "published_at": item.get("published_at"),
        "fetched_at": item.get("fetched_at"),
        "collector": item.get("collector"),
        "official_source": bool(item.get("official_source", False)),
        "language": item.get("language"),
        "trust_tier": item.get("trust_tier"),
        "source_tier": item.get("source_tier"),
        "source_role": item.get("source_role"),
        "source_format": item.get("source_format"),
        "source_id": item.get("source_id"),
        "source_name": item.get("source_name"),
        "dedupe_key": item.get("dedupe_key"),
        "same_event_cluster_id": same_event_cluster_id,
        "same_event_cluster_rank": same_event_cluster_rank,
        "same_event_cluster_size": same_event_cluster_size,
        "same_event_cluster_primary_id": same_event_cluster_primary_id,
        "primary_domain": primary_domain,
        "secondary_domains": secondary_domains,
        "topics": topics,
        "entities": entities,
        "content_type": _content_type(text),
        "geography": _geography(text),
        "confidence": round(confidence, 2),
        "needs_human_review": needs_human_review,
        "fetch_required": not skip_fulltext,
        "fetch_priority": 0.0 if skip_fulltext else fetch_priority,
        "fetch_hints": {
            "prefer_fulltext": not skip_fulltext,
            "prefer_primary_source": bool(item.get("official_source", False)),
            "cluster_primary": bool(item.get("title_cluster_is_primary", False)),
            "skip_reason": "blocked_source" if skip_fulltext else None,
        },
        "reason": (
            f"Skipping fulltext for blocked source {item.get('feed_title')}."
            if skip_fulltext
            else f"Heuristic classifier matched keywords for {primary_domain}."
        ),
    }
    return ClassificationResult(row=row)


def _chunked(items: list[dict], chunk_size: int) -> list[list[dict]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _parallel_classify(items: list[dict], chunk_size: int, max_workers: int | None) -> list[dict]:
    chunks = _chunked(items, chunk_size)
    if not chunks:
        return []
    if len(chunks) == 1:
        return [classify_item(item).row for item in chunks[0]]
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers or min(len(chunks), (os.cpu_count() or 1) + 4)) as executor:
        for chunk in executor.map(lambda chunk: [classify_item(item).row for item in chunk], chunks):
            results.extend(chunk)
    return results


def classify_articles(items: Iterable[dict], chunk_size: int = 32, max_workers: int | None = None) -> list[dict]:
    items_list = list(items)
    return _parallel_classify(items_list, chunk_size, max_workers)


def _merge_manifest_row(item: dict, label: dict) -> dict:
    merged = dict(item)
    merged.update(label)
    for key in ("id", "article_id", "title", "url", "canonical_url", "feed_url", "feed_title", "published_at", "fetched_at", "collector", "official_source", "language", "trust_tier", "source_tier", "source_role", "source_format", "source_id", "source_name", "dedupe_key"):
        if key in item and merged.get(key) is None:
            merged[key] = item.get(key)
    if not merged.get("canonical_url") and merged.get("url"):
        merged["canonical_url"] = merged["url"]
    return merged


def run_article_classifier(
    input_path: str = "data/news_items_deduped.jsonl",
    output_path: str = "data/news_item_labels.jsonl",
    cluster_threshold: float = 0.86,
    chunk_size: int = 32,
    max_workers: int | None = None,
) -> list[dict]:
    items = read_jsonl(input_path)
    clustered_items = cluster_title_similar_items(items, threshold=cluster_threshold)
    try:
        labels = classify_articles(clustered_items, chunk_size=chunk_size, max_workers=max_workers)
    except TypeError:
        labels = classify_articles(clustered_items)
    merged = [_merge_manifest_row(item, label) for item, label in zip(clustered_items, labels)]
    write_jsonl(output_path, merged)
    return merged
