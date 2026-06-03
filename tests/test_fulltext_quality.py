"""Tests for fulltext quality scoring."""
from __future__ import annotations

from news_system.processors.fulltext_quality import compute_fulltext_quality


class TestComputeFulltextQuality:
    def test_empty_content_returns_zero(self):
        score, length = compute_fulltext_quality(None, "not_attempted")
        assert score == 0.0

    def test_empty_string_returns_zero(self):
        score, length = compute_fulltext_quality("", "not_attempted")
        assert score == 0.0

    def test_status_empty_returns_zero(self):
        score, length = compute_fulltext_quality("some content", "empty")
        assert score == 0.0

    def test_status_timeout_returns_zero(self):
        score, length = compute_fulltext_quality("some content", "timeout")
        assert score == 0.0

    def test_status_error_returns_zero(self):
        score, length = compute_fulltext_quality("some content", "error")
        assert score == 0.0

    def test_short_content_under_300(self):
        text = "A" * 150
        score, length = compute_fulltext_quality(text, "extracted")
        assert score == 0.2
        assert length == 150

    def test_content_300_to_500(self):
        text = "A" * 400
        score, length = compute_fulltext_quality(text, "extracted")
        assert score == 0.4
        assert length == 400

    def test_content_500_to_1500(self):
        text = "A" * 1000
        score, length = compute_fulltext_quality(text, "extracted")
        assert score == 0.6
        assert length == 1000

    def test_content_over_1500(self):
        text = "A" * 2000
        score, length = compute_fulltext_quality(text, "extracted")
        assert score == 0.8
        assert length == 2000

    def test_boilerplate_noise_caps_at_07(self):
        # High noise ratio should cap at 0.7
        text = (
            "Subscribe now to read more. "
            "Click here for more information. "
            "Related articles you might like. "
            "All rights reserved by the publisher. "
            "Terms of service apply. "
            "Privacy policy. "
            "Advertisement. Read our newsletter. "
            "Sign up for updates. Log in to continue. "
            * 10
        )
        score, length = compute_fulltext_quality(text, "extracted")
        # With ~10 boilerplate hits and high ratio, should be capped at 0.7
        assert score <= 0.7
        assert score > 0

    def test_barely_over_1500_still_08(self):
        text = "A" * 1501
        score, length = compute_fulltext_quality(text, "extracted")
        assert score == 0.8

    def test_edge_300_exact(self):
        text = "A" * 299
        score, length = compute_fulltext_quality(text, "extracted")
        assert score == 0.2

    def test_edge_500_exact(self):
        text = "A" * 500
        score, length = compute_fulltext_quality(text, "extracted")
        assert score == 0.6  # 500 >= 500, so 500-1500 range = 0.6

    def test_edge_1500_exact(self):
        text = "A" * 1500
        score, length = compute_fulltext_quality(text, "extracted")
        assert score == 0.8  # 1500 >= 1500 → 0.8

    def test_blocked_status_returns_zero(self):
        score, length = compute_fulltext_quality("content", "blocked")
        assert score == 0.0
        assert length == 0

    def test_paywalled_status_returns_low_score(self):
        score, length = compute_fulltext_quality("content", "paywalled")
        assert score == 0.2
        assert length == 7

    def test_partial_content_short(self):
        score, length = compute_fulltext_quality("short", "partial")
        assert score == 0.2
        assert length == 5

    def test_long_clean_article_returns_high_score(self):
        text = "A" * 2000
        score, length = compute_fulltext_quality(text, "extracted")
        assert score == 0.8
        assert length == 2000

    def test_boilerplate_noise_caps_score(self):
        # High noise ratio should cap at 0.7
        text = (
            "Subscribe now to read more. "
            "Click here for more information. "
            "Related articles you might like. "
            "All rights reserved by the publisher. "
            "Terms of service apply. "
            "Privacy policy. "
            "Advertisement. Read our newsletter. "
            "Sign up for updates. Log in to continue. "
            * 10
        )
        score, length = compute_fulltext_quality(text, "extracted")
        # With ~10 boilerplate hits and high ratio, should be capped at 0.7
        assert score <= 0.7
        assert score > 0
