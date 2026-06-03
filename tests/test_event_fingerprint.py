"""Tests for event fingerprint generation and overlap detection."""
from __future__ import annotations

from datetime import datetime, timezone

from news_system.processors.event_fingerprint import (
    date_bucket,
    extract_top_entities,
    extract_top_keywords,
    fingerprint_overlap,
    generate_fingerprint,
)


class TestDateBucket:
    def test_with_datetime(self):
        dt = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
        assert date_bucket(dt) == "2026-06-03"

    def test_with_none(self):
        bucket = date_bucket(None)
        # Should return today
        assert bucket == datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def test_format(self):
        dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert date_bucket(dt) == "2026-01-01"


class TestExtractTopEntities:
    def test_empty_list(self):
        assert extract_top_entities([]) == []

    def test_few_entities(self):
        assert extract_top_entities(["US", "China"]) == ["us", "china"]

    def test_max_three(self):
        entities = ["A", "B", "C", "D", "E"]
        assert len(extract_top_entities(entities)) == 3

    def test_case_normalization(self):
        assert extract_top_entities(["USA"]) == ["usa"]

    def test_with_set(self):
        assert extract_top_entities({"US", "China"})  # no error


class TestExtractTopKeywords:
    def test_empty(self):
        assert extract_top_keywords([]) == []

    def test_max_five(self):
        kws = [str(i) for i in range(10)]
        assert len(extract_top_keywords(kws)) == 5

    def test_case_normalization(self):
        assert extract_top_keywords(["War"]) == ["war"]


class TestGenerateFingerprint:
    def test_basic_format(self):
        fp = generate_fingerprint(
            category="war_conflict",
            dt=datetime(2026, 6, 3, tzinfo=timezone.utc),
            entities=["US", "Iran"],
            keywords=["war", "missile", "strike"],
        )
        # Expected: war_conflict|2026-06-03|us,iran|war,missile,strike
        parts = fp.split("|")
        assert len(parts) == 4
        assert parts[0] == "war_conflict"
        assert parts[1] == "2026-06-03"
        assert "us" in parts[2]
        assert "iran" in parts[2]

    def test_category_only(self):
        fp = generate_fingerprint(category="disaster", dt=None)
        parts = fp.split("|")
        assert parts[0] == "disaster"

    def test_none_category_defaults_to_unknown(self):
        fp = generate_fingerprint(category=None, dt=None)
        assert fp.startswith("unknown|")

    def test_no_entities_or_keywords(self):
        fp = generate_fingerprint(category="politics", dt=datetime(2026, 6, 3, tzinfo=timezone.utc))
        parts = fp.split("|")
        assert parts[2] == ""
        assert parts[3] == ""

    def test_fingerprint_uses_collected_at_when_published_at_missing(self):
        fp = generate_fingerprint(
            category="tech", dt=None,
            collected_at=datetime(2026, 6, 3, tzinfo=timezone.utc),
        )
        parts = fp.split("|")
        assert parts[1] == "2026-06-03"

    def test_fingerprint_falls_back_to_source_country_when_entities_empty(self):
        fp = generate_fingerprint(
            category="politics", dt=datetime.now(timezone.utc),
            entities=[], source_country="iran",
        )
        parts = fp.split("|")
        assert "iran" in parts[2]

    def test_fingerprint_falls_back_to_title_tokens_when_keywords_missing(self):
        fp = generate_fingerprint(
            category="war", dt=datetime.now(timezone.utc),
            keywords=[], normalized_title="Iran launches missile strike on Israel",
        )
        parts = fp.split("|")
        assert len(parts[3]) > 0

    def test_fingerprint_stable_with_different_entity_order(self):
        dt = datetime.now(timezone.utc)
        fp1 = generate_fingerprint(
            category="politics", dt=dt,
            entities=["Iran", "US"],
        )
        fp2 = generate_fingerprint(
            category="politics", dt=dt,
            entities=["US", "Iran"],
        )
        assert fp1 == fp2


class TestFingerprintOverlap:
    def test_identical_fingerprints(self):
        dt = datetime(2026, 6, 3, tzinfo=timezone.utc)
        fp1 = generate_fingerprint(
            category="war_conflict", dt=dt,
            entities=["US", "Iran"], keywords=["war", "missile"],
        )
        fp2 = generate_fingerprint(
            category="war_conflict", dt=dt,
            entities=["US", "Iran"], keywords=["war", "missile"],
        )
        assert fingerprint_overlap(fp1, fp2) == 1.0

    def test_different_categories(self):
        dt = datetime(2026, 6, 3, tzinfo=timezone.utc)
        fp1 = generate_fingerprint(category="war_conflict", dt=dt)
        fp2 = generate_fingerprint(category="politics", dt=dt)
        assert fingerprint_overlap(fp1, fp2) == 0.0

    def test_different_dates(self):
        fp1 = generate_fingerprint(
            category="politics",
            dt=datetime(2026, 6, 3, tzinfo=timezone.utc),
        )
        fp2 = generate_fingerprint(
            category="politics",
            dt=datetime(2026, 6, 4, tzinfo=timezone.utc),
        )
        assert fingerprint_overlap(fp1, fp2) == 0.0

    def test_same_category_date_sufficient_entity_keyword_overlap(self):
        dt = datetime(2026, 6, 3, tzinfo=timezone.utc)
        fp1 = generate_fingerprint(
            category="war_conflict", dt=dt,
            entities=["US", "Iran", "Israel"],
            keywords=["war", "missile", "strike", "attack", "conflict"],
        )
        fp2 = generate_fingerprint(
            category="war_conflict", dt=dt,
            entities=["US", "Iran", "Lebanon"],
            keywords=["war", "missile", "truce", "ceasefire", "attack"],
        )
        # Entities: US,Iran overlap 2/4 = 0.5 ✓
        # Keywords: war,missile,attack overlap 3/7 = 0.42 ✓ (>= 0.4)
        assert fingerprint_overlap(fp1, fp2) == 1.0

    def test_insufficient_entity_overlap(self):
        dt = datetime(2026, 6, 3, tzinfo=timezone.utc)
        fp1 = generate_fingerprint(
            category="war_conflict", dt=dt,
            entities=["US", "Iran"],
            keywords=["war", "missile"],
        )
        fp2 = generate_fingerprint(
            category="war_conflict", dt=dt,
            entities=["China", "Russia"],
            keywords=["war", "missile"],
        )
        # Entities: 0 overlap / 4 total = 0.0 < 0.5
        assert fingerprint_overlap(fp1, fp2) == 0.0

    def test_insufficient_keyword_overlap(self):
        dt = datetime(2026, 6, 3, tzinfo=timezone.utc)
        fp1 = generate_fingerprint(
            category="war_conflict", dt=dt,
            entities=["US", "Iran"],
            keywords=["war", "missile"],
        )
        fp2 = generate_fingerprint(
            category="war_conflict", dt=dt,
            entities=["US", "Iran"],
            keywords=["economy", "trade"],
        )
        # Entities: 2/2 = 1.0 ✓ (>= 0.5)
        # Keywords: 0/4 = 0.0 < 0.4 ✗
        assert fingerprint_overlap(fp1, fp2) == 0.0

    def test_fingerprint_similarity_merges_related_events(self):
        dt = datetime(2026, 6, 3, tzinfo=timezone.utc)
        fp1 = generate_fingerprint(
            category="war_conflict", dt=dt,
            entities=["Iran", "US", "Israel"],
            keywords=["missile", "strike", "attack", "war"],
        )
        fp2 = generate_fingerprint(
            category="war_conflict", dt=dt,
            entities=["Iran", "US", "Lebanon"],
            keywords=["missile", "strike", "attack", "truce"],
        )
        # Entities: iran,us overlap 2/4 = 0.5 ✓ (>= 0.5)
        # Keywords: missile,strike,attack overlap 3/5 = 0.6 ✓ (>= 0.4)
        assert fingerprint_overlap(fp1, fp2) == 1.0

    def test_malformed_fingerprint(self):
        assert fingerprint_overlap("bad", "also_bad") == 0.0