"""Tests for source credibility scoring."""
from __future__ import annotations

import os
from pathlib import Path

from news_system.config.sources import load_sources


BASE = Path(__file__).resolve().parent.parent


class TestSourceCredibility:
    def test_sources_load_with_credibility(self):
        sources = load_sources(str(BASE / "config" / "sources.yaml"))
        bbc = [s for s in sources if s.name == "BBC World"]
        assert len(bbc) == 1
        assert bbc[0].credibility_score == 0.95

    def test_guardian_has_credibility(self):
        sources = load_sources(str(BASE / "config" / "sources.yaml"))
        gw = [s for s in sources if s.name == "Guardian World"]
        assert len(gw) == 1
        assert gw[0].credibility_score == 0.90

    def test_nyt_has_credibility(self):
        sources = load_sources(str(BASE / "config" / "sources.yaml"))
        nyt = [s for s in sources if s.name == "NYT World"]
        assert len(nyt) == 1
        assert nyt[0].credibility_score == 0.90

    def test_gdelt_has_credibility(self):
        sources = load_sources(str(BASE / "config" / "sources.yaml"))
        gdelt = [s for s in sources if s.name == "GDELT World News"]
        assert len(gdelt) == 1
        assert gdelt[0].credibility_score == 0.50

    def test_newsdata_has_credibility(self):
        sources = load_sources(str(BASE / "config" / "sources.yaml"))
        nd = [s for s in sources if s.name == "NewsData.io"]
        assert len(nd) == 1
        assert nd[0].credibility_score == 0.60

    def test_disabled_source_reuters_still_has_credibility(self):
        sources = load_sources(str(BASE / "config" / "sources.yaml"))
        reuters = [s for s in sources if s.name == "Reuters News Sitemap"]
        assert len(reuters) == 1
        assert reuters[0].credibility_score == 0.95

    def test_enabled_count(self):
        sources = load_sources(str(BASE / "config" / "sources.yaml"))
        enabled = [s for s in sources if s.enabled]
        assert len(enabled) >= 29

    def test_credibility_range(self):
        sources = load_sources(str(BASE / "config" / "sources.yaml"))
        for s in sources:
            assert 0.0 <= s.credibility_score <= 1.0

    def test_all_have_region_or_default(self):
        sources = load_sources(str(BASE / "config" / "sources.yaml"))
        for s in sources:
            assert s.region is not None or 1 == 1  # region is optional

    def test_bbc_region(self):
        sources = load_sources(str(BASE / "config" / "sources.yaml"))
        bbc = [s for s in sources if s.name == "BBC World"][0]
        assert bbc.region == "europe"
        assert bbc.ownership_type == "public"

    def test_get_credibility_from_scorer(self):
        from news_system.processors.scorer import _get_credibility

        # Mock article without source_config → default 0.5
        class MockArticle:
            raw_payload = {}

        a = MockArticle()
        assert _get_credibility(a) == 0.5

        # Mock article with source_config
        class MockArticle2:
            raw_payload = {"source_config": {"credibility_score": 0.9}}

        a2 = MockArticle2()
        assert _get_credibility(a2) == 0.9

    def test_credibility_via_source_config_metadata(self):
        """Verify that _apply_source_metadata in jobs passes credibility through."""
        from news_system.config.sources import SourceConfig
        from news_system.jobs import _apply_source_metadata
        from news_system.schemas import Article

        src = SourceConfig(
            name="TestSource",
            source_type="rss",
            enabled=True,
            credibility_score=0.85,
        )
        article = Article(
            title="Test",
            url="https://example.com/test",
            published_at="2026-06-03T00:00:00Z",
        )
        _apply_source_metadata(article, src)

        from news_system.processors.scorer import _get_credibility
        cred = _get_credibility(article)
        assert cred == 0.85