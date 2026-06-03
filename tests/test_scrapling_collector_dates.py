from __future__ import annotations

from datetime import datetime, timezone

from news_system.collectors.scrapling_collector import ScraplingPlaywrightCollector


class FakeElement:
    def __init__(self, text: str = "", attrs: dict[str, str] | None = None):
        self.text = text
        self.attrs = attrs or {}

    def inner_text(self) -> str:
        return self.text

    def get_attribute(self, name: str) -> str | None:
        return self.attrs.get(name)


class FakePage:
    def __init__(self, selectors: dict[str, list[FakeElement]]):
        self.selectors = selectors

    def query_selector_all(self, selector: str):
        return self.selectors.get(selector, [])

    def query_selector(self, selector: str):
        items = self.query_selector_all(selector)
        return items[0] if items else None


def test_extract_published_at_prefers_article_datetime_metadata():
    page = FakePage({
        "meta[property='article:published_time'], meta[name='article:published_time'], meta[name='pubdate'], meta[name='publishdate'], meta[name='date'], meta[itemprop='datePublished']": [
            FakeElement(attrs={"content": "2026-06-03T09:30:00+08:00"})
        ]
    })

    dt, source = ScraplingPlaywrightCollector._extract_published_at(page)

    assert dt == datetime(2026, 6, 3, 1, 30, tzinfo=timezone.utc)
    assert source == "page_metadata"


def test_extract_published_at_returns_none_when_no_article_date_parseable():
    page = FakePage({
        "time[datetime]": [FakeElement(attrs={"datetime": "not a date"})],
        "time": [FakeElement(text="Updated recently")],
    })

    dt, source = ScraplingPlaywrightCollector._extract_published_at(page)

    assert dt is None
    assert source is None


def test_build_article_uses_sentinel_and_metadata_when_date_missing():
    collected_at = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)

    article = ScraplingPlaywrightCollector._build_article(
        title="Old undated page",
        url="https://example.com/news/old",
        summary="summary",
        source_name="Example",
        parsed_published_at=None,
        date_source=None,
        collected_at=collected_at,
    )

    assert article.published_at == ScraplingPlaywrightCollector.UNKNOWN_PUBLISHED_AT_SENTINEL
    assert article.published_at != collected_at
    assert article.raw["date_parse_status"] == "missing"
    assert article.raw["date_source"] == "fallback_sentinel"
    assert article.raw["collected_at"] == collected_at.isoformat()


def test_build_article_uses_parsed_article_date_and_metadata_when_available():
    parsed = datetime(2026, 6, 3, 1, 30, tzinfo=timezone.utc)
    collected_at = datetime(2026, 6, 3, 12, 0, tzinfo=timezone.utc)

    article = ScraplingPlaywrightCollector._build_article(
        title="Fresh dated article",
        url="https://example.com/news/fresh",
        summary="summary",
        source_name="Example",
        parsed_published_at=parsed,
        date_source="page_metadata",
        collected_at=collected_at,
    )

    assert article.published_at == parsed
    assert article.raw["date_parse_status"] == "parsed"
    assert article.raw["date_source"] == "page_metadata"
