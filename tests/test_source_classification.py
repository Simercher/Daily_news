from __future__ import annotations

from news_feed_bootstrap.source_classification import is_official_source


def test_official_source_matches_allowlisted_domain(tmp_path) -> None:
    config = tmp_path / "official.yaml"
    config.write_text(
        "official_domains:\n"
        "  - example-news.com\n"
        "official_title_patterns: []\n",
        encoding="utf-8",
    )

    assert is_official_source(feed_url="https://rss.example-news.com/world.xml", config_path=str(config)) is True


def test_official_source_matches_allowlisted_title_when_feedburner_hides_domain(tmp_path) -> None:
    config = tmp_path / "official.yaml"
    config.write_text(
        "official_domains: []\n"
        "official_title_patterns:\n"
        "  - Example Daily\n",
        encoding="utf-8",
    )

    assert (
        is_official_source(
            feed_url="https://feeds.feedburner.com/example",
            feed_title="Example Daily :: News Feed",
            config_path=str(config),
        )
        is True
    )


def test_unknown_blog_is_not_official_source(tmp_path) -> None:
    config = tmp_path / "official.yaml"
    config.write_text(
        "official_domains:\n"
        "  - example-news.com\n"
        "official_title_patterns:\n"
        "  - Example Daily\n",
        encoding="utf-8",
    )

    assert (
        is_official_source(
            feed_url="https://personal-blog.example/rss.xml",
            feed_title="My Blog",
            config_path=str(config),
        )
        is False
    )
