"""Unit tests for domain_summarizer processor."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from news_system.db.models import ArticleModel, Base
from news_system.processors.domain_summarizer import (
    ArticleSummary,
    CATEGORY_DOMAIN_MAP,
    DOMAIN_KEYWORDS,
    DOMAIN_DISPLAY_NAMES,
    DomainGroup,
    build_domain_summaries,
    classify_article,
    classify_articles,
    classify_articles_with_decisions,
    classify_articles_with_llm,
    format_for_discord,
)


# ---------------------------------------------------------------------------
# Helpers to build test articles quickly
# ---------------------------------------------------------------------------

def make_article(
    title: str = "Test article",
    category: str | None = None,
    description: str | None = None,
    content_snippet: str | None = None,
    source_name: str | None = "TestSource",
    source_domain: str | None = "example.com",
    url: str = "https://example.com/test",
    published_at: datetime | None = None,
) -> ArticleModel:
    return ArticleModel(
        title=title,
        category=category,
        description=description,
        content_snippet=content_snippet,
        source_name=source_name,
        source_domain=source_domain,
        url=url,
        published_at=published_at or datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tests: classify_article
# ---------------------------------------------------------------------------

class TestClassifyArticle:
    def test_category_maps_as_fallback_when_content_ambiguous(self):
        """Category mapping is used when content has no domain keywords."""
        for cat, expected in CATEGORY_DOMAIN_MAP.items():
            article = make_article(title="Brief update", category=cat)
            assert classify_article(article) == expected, f"category={cat!r}"

    def test_keyword_matching_when_no_category(self):
        """When category is None/empty, keyword matching is used."""
        article = make_article(
            title="China and Russia sign new trade deal",
            category=None,
        )
        assert classify_article(article) == "international"

    def test_keyword_matching_macro(self):
        """Macro keywords like 'inflation' and 'central bank'."""
        article = make_article(
            title="Fed holds interest rates steady amid inflation concerns",
            category=None,
        )
        assert classify_article(article) == "macro"

    def test_keyword_matching_stocks(self):
        """Stocks keywords like 'nasdaq' and 'earnings'."""
        article = make_article(
            title="Nasdaq hits new high as tech earnings beat estimates",
            category=None,
        )
        assert classify_article(article) == "stocks"

    def test_keyword_matching_tech_ai(self):
        """Tech_AI keywords like 'artificial intelligence'."""
        article = make_article(
            title="OpenAI releases new AI model with improvements",
            category=None,
        )
        assert classify_article(article) == "tech_ai"

    def test_keyword_matching_uses_description_too(self):
        """Keyword matching also checks description."""
        article = make_article(
            title="Daily market update",
            description="The S&P 500 rallied on strong quarterly earnings from banks.",
            category=None,
        )
        assert classify_article(article) == "stocks"

    def test_keyword_matching_uses_content_snippet(self):
        """When description is missing, content_snippet is used."""
        article = make_article(
            title="Daily market update",
            description=None,
            content_snippet="The S&P 500 rallied on strong quarterly earnings from banks.",
            category=None,
        )
        assert classify_article(article) == "stocks"

    def test_chinese_keyword_matching(self):
        """Chinese keywords are correctly matched."""
        article = make_article(
            title="總統召開國安會議討論半導體政策",
            category=None,
        )
        assert classify_article(article) == "international"

    def test_content_keywords_take_priority_over_category(self):
        """Clear content keywords beat source category fallback."""
        article = make_article(
            title="AI chip breakthrough announced by Nvidia",
            description="New semiconductor data center platform accelerates generative AI.",
            category="economy",  # maps to macro, but content clearly matches tech_ai
        )
        assert classify_article(article) == "tech_ai"

    def test_business_category_with_stock_keywords_becomes_stocks(self):
        article = make_article(
            title="Nasdaq rallies as shares jump after earnings",
            description="The S&P 500 rose as stock investors bought ETFs after quarterly results.",
            category="business",
        )
        assert classify_article(article) == "stocks"

    def test_business_category_with_ai_chip_keywords_becomes_tech_ai(self):
        article = make_article(
            title="Nvidia and TSMC expand AI chip production",
            description="Semiconductor demand from data center customers keeps rising.",
            category="business",
        )
        assert classify_article(article) == "tech_ai"

    def test_business_category_with_macro_keywords_becomes_macro(self):
        article = make_article(
            title="Fed rate decision follows inflation and GDP reports",
            description="Central bank officials debate monetary policy after CPI data.",
            category="business",
        )
        assert classify_article(article) == "macro"

    def test_world_category_market_content_is_not_forced_international(self):
        article = make_article(
            title="Nasdaq and S&P 500 rally as earnings lift shares",
            description="Stock market investors increased ETF exposure after strong quarterly results.",
            category="world",
        )
        assert classify_article(article) == "stocks"

    def test_world_category_tech_content_is_not_forced_international(self):
        article = make_article(
            title="Nvidia unveils AI chip for data center customers",
            description="The semiconductor platform targets cloud and generative AI workloads.",
            category="world",
        )
        assert classify_article(article) == "tech_ai"

    def test_ambiguous_article_falls_back_to_category_mapping(self):
        article = make_article(
            title="Company leaders meet for annual outlook",
            description="Executives discussed plans for the coming year.",
            category="business",
        )
        assert classify_article(article) == "macro"

    def test_no_match_returns_other(self):
        """No category and no keyword match returns 'other'."""
        article = make_article(
            title="Local community event this weekend",
            category="lifestyle",
        )
        assert classify_article(article) == "other"

    def test_empty_title_and_description(self):
        """Empty fields gracefully handled."""
        article = make_article(title="", description=None, category=None)
        assert classify_article(article) == "other"


# ---------------------------------------------------------------------------
# Tests: classify_articles
# ---------------------------------------------------------------------------

class TestClassifyArticles:
    def test_groups_articles_by_domain(self):
        articles = [
            make_article(title="US election results", category="world"),
            make_article(title="Inflation rises", category="economy"),
            make_article(title="Nasdaq rally", category="markets"),
            make_article(title="Local event", category="lifestyle"),
        ]
        groups = classify_articles(articles)
        assert set(groups.keys()) == {"international", "macro", "stocks", "tech_ai", "other"}
        assert len(groups["international"]) == 1
        assert len(groups["macro"]) == 1
        assert len(groups["stocks"]) == 1
        assert len(groups["other"]) == 1

    def test_empty_input(self):
        assert classify_articles([]) == {
            "international": [],
            "macro": [],
            "stocks": [],
            "tech_ai": [],
            "other": [],
        }

    def test_all_articles_to_same_domain(self):
        articles = [
            make_article(title="GDP grows", category="economy"),
            make_article(title="Fed rate decision", category="economy"),
        ]
        groups = classify_articles(articles)
        assert len(groups["macro"]) == 2
        assert all(len(v) == 0 for d, v in groups.items() if d != "macro")


# ---------------------------------------------------------------------------
# Tests: LLM classification path
# ---------------------------------------------------------------------------

class TestClassifyArticlesWithLLM:
    def test_fake_llm_overrides_rule_classification_when_valid(self):
        articles = [make_article(title="Fed holds rates", category="economy")]

        def fake_llm(batch):
            assert batch[0]["rule_domain"] == "macro"
            assert batch[0]["title"] == "Fed holds rates"
            return [{"index": batch[0]["index"], "domain": "tech_ai", "confidence": 0.9, "reason": "AI angle"}]

        groups, decisions = classify_articles_with_decisions(articles, llm_classifier=fake_llm)

        assert groups["tech_ai"] == articles
        decision = next(iter(decisions.values()))
        assert decision.domain == "tech_ai"
        assert decision.method == "llm"
        assert decision.rule_domain == "macro"
        assert decision.confidence == 0.9
        assert decision.reason == "AI angle"

    def test_missing_llm_result_falls_back_to_rule_for_that_article(self):
        articles = [
            make_article(title="AI chip breakthrough", category="technology"),
            make_article(title="Nasdaq rally", category="markets"),
        ]

        def fake_llm(batch):
            return [{"index": batch[0]["index"], "domain": "macro"}]

        groups, decisions = classify_articles_with_decisions(articles, llm_classifier=fake_llm)

        assert groups["macro"] == [articles[0]]
        assert groups["stocks"] == [articles[1]]
        assert decisions[articles[1].url].method == "rule"
        assert decisions[articles[1].url].reason == "missing_llm_result"

    def test_invalid_domain_falls_back_to_rule(self):
        articles = [make_article(title="Nasdaq rally", category="markets")]

        def fake_llm(batch):
            return [{"index": batch[0]["index"], "domain": "sports"}]

        groups, decisions = classify_articles_with_decisions(articles, llm_classifier=fake_llm)

        assert groups["stocks"] == articles
        decision = next(iter(decisions.values()))
        assert decision.method == "rule"
        assert decision.rule_domain == "stocks"
        assert "invalid_llm_domain" in decision.reason

    def test_llm_exception_falls_back_to_all_rule_results(self):
        articles = [
            make_article(title="Fed rate decision", category="economy"),
            make_article(title="OpenAI model launch", category="technology"),
        ]

        def fake_llm(batch):
            raise RuntimeError("provider unavailable")

        groups, decisions = classify_articles_with_decisions(articles, llm_classifier=fake_llm)

        assert groups["macro"] == [articles[0]]
        assert groups["tech_ai"] == [articles[1]]
        assert all(d.method == "rule" for d in decisions.values())
        assert all("llm_exception" in d.reason for d in decisions.values())

    def test_batching_works_for_multiple_articles(self):
        articles = [
            make_article(title="Article A", category="world", url="https://example.com/a"),
            make_article(title="Article B", category="economy", url="https://example.com/b"),
            make_article(title="Article C", category="markets", url="https://example.com/c"),
        ]
        seen_batches = []

        def fake_llm(batch):
            seen_batches.append([item["index"] for item in batch])
            return [{"id": item["id"], "domain": "other"} for item in batch]

        groups = classify_articles_with_llm(articles, llm_classifier=fake_llm, batch_size=2)

        assert seen_batches == [[0, 1], [2]]
        assert groups["other"] == articles
        assert all(len(v) == 0 for d, v in groups.items() if d != "other")

    def test_invalid_json_response_falls_back_to_rules(self):
        articles = [make_article(title="GDP grows", category="economy")]

        groups, decisions = classify_articles_with_decisions(articles, llm_classifier=lambda batch: "not json")

        assert groups["macro"] == articles
        decision = next(iter(decisions.values()))
        assert decision.method == "rule"
        assert "llm_exception" in decision.reason


# ---------------------------------------------------------------------------
# Tests: build_domain_summaries
# ---------------------------------------------------------------------------

class TestBuildDomainSummaries:
    def test_returns_correct_structure(self):
        articles = [
            make_article(
                title="US election",
                category="world",
                description="Major election updates",
                url="https://example.com/1",
                source_name="BBC",
                published_at=datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc),
            ),
        ]
        classified = classify_articles(articles)
        result = build_domain_summaries(classified)

        # Check international group
        inter = result["international"]
        assert inter["display_name"] == "國際情勢"
        assert inter["domain"] == "international"
        assert inter["count"] == 1
        assert len(inter["articles"]) == 1
        a = inter["articles"][0]
        assert a["title"] == "US election"
        assert a["url"] == "https://example.com/1"
        assert a["source"] == "BBC"
        assert a["snippet"] == "Major election updates"

    def test_empty_domain_returns_empty_group(self):
        classified = {d: [] for d in ["international", "macro", "stocks", "tech_ai", "other"]}
        result = build_domain_summaries(classified)
        for domain in classified:
            assert result[domain]["count"] == 0
            assert result[domain]["articles"] == []

    def test_all_five_domains_present(self):
        articles = [
            make_article(title="War news", category="world"),
            make_article(title="GDP data", category="economy"),
            make_article(title="Stock rally", category="markets"),
            make_article(title="AI breakthrough", category="technology"),
            make_article(title="Local event", category="lifestyle"),
        ]
        classified = classify_articles(articles)
        result = build_domain_summaries(classified)
        expected_domains = {"international", "macro", "stocks", "tech_ai", "other"}
        assert set(result.keys()) == expected_domains

    def test_max_articles_limit(self):
        articles = [make_article(title=f"Article {i}", category="economy") for i in range(20)]
        classified = classify_articles(articles)
        result = build_domain_summaries(classified, max_articles=5)
        # Only 5 should be in the summary (sorted by published_at desc)
        assert result["macro"]["count"] == 5
        assert len(result["macro"]["articles"]) == 5

    def test_snippet_truncated_to_500_chars(self):
        long_snippet = "x" * 500
        articles = [make_article(title="Test", category="world", description=long_snippet)]
        classified = classify_articles(articles)
        result = build_domain_summaries(classified)
        snippet = result["international"]["articles"][0]["snippet"]
        assert len(snippet) == 500

    def test_source_falls_back_to_source_domain(self):
        articles = [make_article(title="Test", category="world", source_name=None, source_domain="nytimes.com")]
        classified = classify_articles(articles)
        result = build_domain_summaries(classified)
        assert result["international"]["articles"][0]["source"] == "nytimes.com"

    def test_source_falls_back_to_unknown(self):
        articles = [make_article(title="Test", category="world", source_name=None, source_domain=None)]
        classified = classify_articles(articles)
        result = build_domain_summaries(classified)
        assert result["international"]["articles"][0]["source"] == "unknown"


# ---------------------------------------------------------------------------
# Tests: format_for_discord
# ---------------------------------------------------------------------------

class TestFormatForDiscord:
    def test_returns_formatted_message(self):
        articles = [
            make_article(
                title="US election",
                category="world",
                description="Major election updates",
                url="https://example.com/1",
                source_name="BBC",
                published_at=datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc),
            ),
        ]
        classified = classify_articles(articles)
        summaries = build_domain_summaries(classified)
        messages = format_for_discord(summaries)

        assert "international" in messages
        msg = messages["international"]
        assert "國際情勢" in msg
        assert "1 則" in msg
        assert "US election" in msg
        assert "BBC" in msg
        assert "Major election updates" in msg

    def test_empty_domains_skipped(self):
        classified = {d: [] for d in ["international", "macro", "stocks", "tech_ai", "other"]}
        summaries = build_domain_summaries(classified)
        messages = format_for_discord(summaries)
        assert messages == {}

    def test_multiple_articles_formatted(self):
        articles = [
            make_article(title="First", category="world", description="Desc A", url="https://a.com/1"),
            make_article(title="Second", category="world", description="Desc B", url="https://a.com/2"),
        ]
        classified = classify_articles(articles)
        summaries = build_domain_summaries(classified)
        messages = format_for_discord(summaries)

        assert "international" in messages
        msg = messages["international"]
        assert "2 則" in msg
        assert "**1. [" in msg
        assert "**2. [" in msg
        assert "Desc A" in msg
        assert "Desc B" in msg


# ---------------------------------------------------------------------------
# Tests: dataclass construction
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_article_summary(self):
        s = ArticleSummary(title="T", url="U", source="S", snippet="Snip", published_at="now")
        assert s.title == "T"
        assert s.url == "U"
        assert s.source == "S"

    def test_domain_group(self):
        g = DomainGroup(domain="macro", display_name="金融總經")
        assert g.domain == "macro"
        assert g.display_name == "金融總經"
        assert g.articles == []

    def test_domain_group_with_articles(self):
        s = ArticleSummary(title="T", url="U", source="S", snippet="Snip", published_at="now")
        g = DomainGroup(domain="macro", display_name="金融總經", articles=[s])
        assert len(g.articles) == 1