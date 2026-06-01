from datetime import datetime, timezone

from news_rss_pipeline.feed_scorer import score_feed
from news_rss_pipeline.models import FeedCandidate, FeedValidationResult


def validation(**overrides):
    data = dict(feed_url="https://example.com/rss.xml", status="active", http_status=200, content_type="application/rss+xml", parse_ok=True, feed_title="Feed", entry_count=20, last_published_at=datetime.now(timezone.utc), items_7d=5, items_30d=20, has_title_rate=1, has_link_rate=1, has_pub_date_rate=1, duplicate_url_rate=0, has_summary_rate=1, has_full_content_rate=0.5, checked_at=datetime.now(timezone.utc))
    data.update(overrides)
    return FeedValidationResult(**data)


def test_high_quality_official_source_scores_high() -> None:
    candidate = FeedCandidate(publisher="UN News", feed_url="https://example.com/rss.xml", discovered_from="manual_official", official=True, publisher_type="official_org", priority="high")
    score = score_feed(candidate, validation())
    assert score.decision == "accept_core_source"
    assert score.total_score >= 85


def test_unknown_source_total_not_too_high() -> None:
    candidate = FeedCandidate(publisher=None, feed_url="https://example.com/rss.xml", discovered_from="third_party_generated", publisher_type="unknown")
    score = score_feed(candidate, validation())
    assert score.total_score < 70


def test_parse_failed_feed_score_zero() -> None:
    candidate = FeedCandidate(publisher="Example", feed_url="https://example.com/rss.xml", discovered_from="homepage_alternate_link", publisher_type="mainstream_media")
    score = score_feed(candidate, validation(status="parse_failed", parse_ok=False))
    assert score.feed_score == 0
