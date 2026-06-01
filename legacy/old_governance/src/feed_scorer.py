from __future__ import annotations

from .config import read_yaml, write_yaml
from .models import FeedCandidate, FeedScore, FeedValidationResult
from .utils import read_jsonl

BASE_SOURCE_SCORES = {
    "official_org": 95,
    "wire_agency": 95,
    "public_broadcaster": 90,
    "mainstream_media": 85,
    "specialized_media": 75,
    "aggregator": 60,
    "unknown": 40,
    "content_farm": 10,
}


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def compute_source_score(candidate: FeedCandidate) -> tuple[float, list[str]]:
    reasons: list[str] = []
    publisher_type = candidate.publisher_type or "unknown"
    score = BASE_SOURCE_SCORES.get(publisher_type, BASE_SOURCE_SCORES["unknown"])
    reasons.append(f"publisher_type={publisher_type}")
    if candidate.official:
        score += 5
        reasons.append("official=true")
    if getattr(candidate, "priority", None) == "high":
        score += 5
    elif getattr(candidate, "priority", None) == "medium_high":
        score += 2
    if candidate.discovered_from in {"official_feed_page", "manual_official"}:
        score += 5
        reasons.append("official discovery")
    if candidate.discovered_from == "third_party_generated":
        score -= 20
        reasons.append("third_party_generated")
    if not candidate.publisher:
        score -= 15
        reasons.append("publisher unknown")
    return clamp(score), reasons


def compute_feed_score(validation: FeedValidationResult) -> tuple[float, list[str]]:
    reasons: list[str] = []
    if validation.status == "parse_failed":
        return 0, ["parse_failed"]

    score = 0.0
    checks = [
        (validation.parse_ok, 25, "parse_ok"),
        (validation.http_status == 200, 15, "http_200"),
        (validation.items_7d > 0, 15, "recent_7d"),
        (validation.items_30d >= 10, 10, "active_30d"),
        (validation.has_title_rate >= 0.95, 10, "title_complete"),
        (validation.has_link_rate >= 0.95, 10, "link_complete"),
        (validation.has_pub_date_rate >= 0.8, 10, "pub_dates"),
        (validation.duplicate_url_rate <= 0.1, 5, "low_duplicates"),
        (validation.has_summary_rate >= 0.7, 5, "summaries"),
        (validation.has_full_content_rate >= 0.3, 5, "rss_content"),
    ]
    for passed, points, reason in checks:
        if passed:
            score += points
            reasons.append(reason)
    if validation.status == "blocked":
        score = min(score, 20)
        reasons.append("blocked")
    if validation.items_30d == 0:
        score -= 30
        reasons.append("no_items_30d")
    if validation.duplicate_url_rate > 0.3:
        score -= 20
        reasons.append("high_duplicates")
    if validation.has_pub_date_rate < 0.5:
        score -= 10
        reasons.append("missing_pub_dates")
    return clamp(score), reasons


def score_feed(candidate: FeedCandidate, validation: FeedValidationResult) -> FeedScore:
    source_score, source_reasons = compute_source_score(candidate)
    feed_score, feed_reasons = compute_feed_score(validation)
    total_score = round(source_score * 0.7 + feed_score * 0.3, 2)
    if total_score >= 85 and feed_score >= 70:
        decision = "accept_core_source"
    elif total_score >= 70 and feed_score >= 60:
        decision = "accept_aux_source"
    elif total_score >= 50:
        decision = "candidate_review"
    else:
        decision = "reject"
    return FeedScore(feed_url=candidate.feed_url, source_score=source_score, feed_score=feed_score, total_score=total_score, decision=decision, reasons=source_reasons + feed_reasons)


def score_discovered(discovered_path: str = "data/discovered_feeds.yaml", health_path: str = "data/feed_health.jsonl", output_path: str = "data/scored_feeds.yaml") -> list[dict]:
    candidates = [FeedCandidate(**row) for row in (read_yaml(discovered_path, {"feeds": []}).get("feeds") or [])]
    validations = {row["feed_url"]: FeedValidationResult(**row) for row in read_jsonl(health_path)}
    scored: list[dict] = []
    for candidate in candidates:
        validation = validations.get(candidate.feed_url)
        if not validation:
            continue
        score = score_feed(candidate, validation)
        scored.append({
            **candidate.model_dump(mode="json"),
            "validation": validation.model_dump(mode="json"),
            "score": score.model_dump(mode="json"),
            "source_score": score.source_score,
            "feed_score": score.feed_score,
            "total_score": score.total_score,
            "decision": score.decision,
        })
    write_yaml(output_path, {"feeds": scored})
    return scored
