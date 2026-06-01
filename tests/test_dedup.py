from news_feed_bootstrap.dedup import compute_item_id, normalize_url


def test_normalize_url_removes_tracking_params() -> None:
    normalized = normalize_url("https://example.com/a?utm_source=x&id=1&fbclid=y#section")
    assert normalized == "https://example.com/a?id=1"


def test_same_normalized_url_has_same_id() -> None:
    first = compute_item_id("https://example.com/a?utm_medium=x&id=1")
    second = compute_item_id("https://example.com/a?id=1")
    assert first == second
