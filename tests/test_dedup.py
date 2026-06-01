from datetime import UTC, datetime

from news_feed_bootstrap.dedup import compute_item_id, deduplicate_items, normalize_url
from news_feed_bootstrap.models import NewsItem


def test_normalize_url_removes_tracking_params() -> None:
    normalized = normalize_url("https://example.com/a?utm_source=x&id=1&fbclid=y#section")
    assert normalized == "https://example.com/a?id=1"


def test_same_normalized_url_has_same_id() -> None:
    first = compute_item_id("https://example.com/a?utm_medium=x&id=1")
    second = compute_item_id("https://example.com/a?id=1")
    assert first == second


def test_normalize_url_canonicalizes_host_port_path_and_query_order() -> None:
    normalized = normalize_url(" HTTPS://Example.COM:443/a/?b=2&a=1 ")
    assert normalized == "https://example.com/a?a=1&b=2"


def test_normalize_url_keeps_non_default_port_and_root_path() -> None:
    normalized = normalize_url("http://Example.COM:8080/")
    assert normalized == "http://example.com:8080/"


def test_normalize_url_removes_common_tracking_params_case_insensitively() -> None:
    normalized = normalize_url(
        "https://example.com/a?id=1&UTM_CUSTOM=x&mc_cid=y&mc_eid=z&ref=r&ref_src=rs&source=s"
    )
    assert normalized == "https://example.com/a?id=1"


def test_normalize_url_preserves_semantic_query_params() -> None:
    normalized = normalize_url("https://example.com/search?page=2&q=rss")
    assert normalized == "https://example.com/search?page=2&q=rss"


def test_deduplicate_items_keeps_first_item_for_same_normalized_url() -> None:
    fetched_at = datetime.now(UTC)
    first = NewsItem(
        id="first",
        title="First",
        url="https://Example.com:443/a/?id=1&utm_source=x",
        feed_url="https://example.com/feed.xml",
        fetched_at=fetched_at,
        content_level="summary_only",
        fetch_status="rss_only",
    )
    duplicate = NewsItem(
        id="duplicate",
        title="Duplicate",
        url="https://example.com/a?id=1#section",
        feed_url="https://example.com/another-feed.xml",
        fetched_at=fetched_at,
        content_level="summary_only",
        fetch_status="rss_only",
    )

    assert deduplicate_items([first, duplicate]) == [first]
