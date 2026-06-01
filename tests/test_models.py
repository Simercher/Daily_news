from datetime import UTC, datetime

from news_feed_bootstrap.models import ActiveFeed, NewsItem, SeedSource


def test_seed_source_create() -> None:
    source = SeedSource(id="feeds", name="Feeds", type="opml", url="https://example.com/list.opml", priority="high")
    assert source.name == "Feeds"
    assert source.type == "opml"
    assert source.enabled is True


def test_seed_source_can_be_disabled() -> None:
    source = SeedSource(id="feeds", name="Feeds", type="opml", url="https://example.com/list.opml", enabled=False)
    assert source.enabled is False


def test_active_feed_create() -> None:
    feed = ActiveFeed(feed_url="https://example.com/rss.xml", checked_at=datetime.now(UTC))
    assert feed.feed_url == "https://example.com/rss.xml"
    assert feed.official_source is False


def test_news_item_create() -> None:
    item = NewsItem(
        id="abc",
        title="Title",
        url="https://example.com/a",
        feed_url="https://example.com/rss.xml",
        fetched_at=datetime.now(UTC),
        content_level="summary_only",
        fetch_status="rss_only",
    )
    assert item.title == "Title"
    assert item.topics == []
    assert item.collector == "local_feedparser"
    assert item.official_source is False
