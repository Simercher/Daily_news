"""Tests for representative article selection."""
from __future__ import annotations

from datetime import datetime, timezone

from news_system.processors.representative_articles import select_representative

MIN_TIME = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _make_article(
    aid: int,
    title: str = "A Representative Article Title That Is Just Right For Testing",
    source_name: str = "SourceA",
    source_domain: str = "source-a.com",
    credibility: float = 0.5,
    fulltext_quality: float = 0.6,
    published_at: datetime | None = None,
    is_duplicate: bool = False,
):
    """Create a mock article object with the needed attributes."""
    pub = published_at or MIN_TIME
    class MockArticle:
        pass

    a = MockArticle()
    a.id = aid
    a.title = title
    a.url = f"https://{source_domain}/article/{aid}"
    a.source_name = source_name
    a.source_domain = source_domain
    a.published_at = pub
    a.is_duplicate = is_duplicate
    a.raw_payload = {"source_config": {"credibility_score": credibility}}
    a.fulltext_quality_score = fulltext_quality
    return a


class TestSelectRepresentative:
    def test_empty_articles_returns_none(self):
        best_id, results = select_representative([])
        assert best_id is None
        assert results == []

    def test_single_article_becomes_representative(self):
        a = _make_article(1)
        best_id, results = select_representative([a])
        assert best_id == 1
        assert len(results) == 1
        assert results[0]["id"] == 1

    def test_duplicates_filtered_out(self):
        a1 = _make_article(1, is_duplicate=False)
        a2 = _make_article(2, title="Another Good Article With Proper Title Length Here", is_duplicate=True)
        best_id, results = select_representative([a1, a2])
        assert len(results) == 1
        assert results[0]["id"] == 1

    def test_all_duplicates_returns_none(self):
        a1 = _make_article(1, is_duplicate=True)
        best_id, results = select_representative([a1])
        assert best_id is None
        assert results == []

    def test_higher_credibility_ranked_first(self):
        a1 = _make_article(1, credibility=0.9)
        a2 = _make_article(2, credibility=0.5)
        best_id, results = select_representative([a1, a2])
        assert best_id == 1

    def test_max_one_per_domain(self):
        a1 = _make_article(1, credibility=0.9, source_domain="example.com")
        a2 = _make_article(2, credibility=0.85, source_domain="example.com")
        a3 = _make_article(3, credibility=0.8, source_domain="other.com")
        best_id, results = select_representative([a1, a2, a3])
        assert len(results) == 2
        assert results[0]["id"] == 1

    def test_max_five_articles(self):
        articles = []
        for i in range(10):
            articles.append(_make_article(i, source_domain=f"src{i}.com", credibility=0.5 + (i / 20)))
        best_id, results = select_representative(articles)
        assert len(results) <= 5

    def test_title_too_short_filtered(self):
        a1 = _make_article(1, credibility=0.9, title="Short")
        a2 = _make_article(2, credibility=0.5, title="A Proper Article Title That Is Just Long Enough For Testing")
        best_id, results = select_representative([a1, a2])
        assert len(results) == 1
        assert results[0]["id"] == 2

    def test_title_too_long_filtered(self):
        a1 = _make_article(1, credibility=0.9, title="X" * 141)
        a2 = _make_article(2, credibility=0.5, title="A Proper Article Title That Is Just Long Enough For Testing")
        best_id, results = select_representative([a1, a2])
        assert len(results) == 1
        assert results[0]["id"] == 2

    def test_title_40_exact(self):
        a1 = _make_article(1, credibility=0.9, title="X" * 39)
        a2 = _make_article(2, credibility=0.5, title="X" * 40)
        best_id, results = select_representative([a1, a2])
        assert len(results) == 1
        assert results[0]["id"] == 2

    def test_title_140_exact(self):
        a1 = _make_article(1, credibility=0.5, title="X" * 140)
        a2 = _make_article(2, credibility=0.9, title="X" * 141)
        best_id, results = select_representative([a1, a2])
        assert len(results) == 1
        assert results[0]["id"] == 1

    def test_result_keys(self):
        a = _make_article(1, credibility=0.9, source_domain="example.com")
        best_id, results = select_representative([a])
        keys = set(results[0].keys())
        assert "id" in keys
        assert "title" in keys
        assert "url" in keys
        assert "source_name" in keys
        assert "credibility_score" in keys
        assert "fulltext_quality_score" in keys
        assert "published_at" in keys