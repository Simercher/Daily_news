import requests

from news_feed_bootstrap.feed_validator import validate_feed


class FakeResponse:
    status_code = 200
    text = """<?xml version="1.0"?><rss version="2.0"><channel><title>Test</title>
    <item><title>A</title><link>https://example.com/a</link>
    <pubDate>Mon, 01 Jun 2026 00:00:00 GMT</pubDate><description>Summary</description></item>
    </channel></rss>"""
    content = text.encode("utf-8")
    headers = {"content-type": "application/rss+xml"}


def test_validate_feed_parses_rss(monkeypatch) -> None:
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse())
    result = validate_feed("https://example.com/rss.xml")
    assert result.parse_ok is True
    assert result.entry_count == 1
    assert result.has_title_rate == 1


class OldFeedResponse:
    status_code = 200
    text = """<?xml version="1.0"?><rss version="2.0"><channel><title>Old</title>
    <item><title>A</title><link>https://example.com/a</link>
    <pubDate>Mon, 01 Jun 2020 00:00:00 GMT</pubDate><description>Summary</description></item>
    </channel></rss>"""
    content = text.encode("utf-8")
    headers = {"content-type": "application/rss+xml"}


def test_validate_feed_marks_inactive_when_no_recent_items(monkeypatch) -> None:
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: OldFeedResponse())
    result = validate_feed("https://example.com/rss.xml")
    assert result.parse_ok is True
    assert result.status == "inactive"
