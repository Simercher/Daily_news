from __future__ import annotations

from pathlib import Path

from news_feed_bootstrap.models import FeedCandidate
from news_feed_bootstrap.opml_importer import import_opml, import_seed_lists


def test_import_opml_falls_back_when_xml_contains_unescaped_ampersand(tmp_path: Path) -> None:
    broken_opml = tmp_path / "broken.opml"
    broken_opml.write_text(
        """<?xml version='1.0' encoding='UTF-8' ?>
<opml version="1.0">
  <body>
    <outline text="World & Nation" title="World & Nation"
      xmlUrl="https://example.com/world.xml" htmlUrl="https://example.com/world" />
    <outline text="Tech" title="Tech" xmlUrl="https://example.com/tech.xml" />
  </body>
</opml>
""",
        encoding="utf-8",
    )

    feeds = import_opml(str(broken_opml))

    assert [feed.feed_url for feed in feeds] == ["https://example.com/world.xml", "https://example.com/tech.xml"]
    assert feeds[0].publisher == "World & Nation"
    assert feeds[0].homepage == "https://example.com/world"


def test_import_seed_lists_skips_disabled_sources(monkeypatch, tmp_path: Path) -> None:
    config = tmp_path / "seed_sources.yaml"
    config.write_text(
        """
seed_sources:
  - id: enabled_source
    name: Enabled Source
    type: opml
    enabled: true
    url: https://example.com/enabled.opml
  - id: disabled_source
    name: Disabled Source
    type: opml
    enabled: false
    url: https://example.com/disabled.opml
""",
        encoding="utf-8",
    )
    imported_urls: list[str] = []

    def fake_import_opml(url: str) -> list[FeedCandidate]:
        imported_urls.append(url)
        return [FeedCandidate(feed_url=f"{url}#feed", discovered_from=url)]

    monkeypatch.setattr("news_feed_bootstrap.opml_importer.import_opml", fake_import_opml)
    monkeypatch.setattr("news_feed_bootstrap.opml_importer.merge_discovered", lambda candidates: candidates)

    feeds = import_seed_lists(str(config))

    assert imported_urls == ["https://example.com/enabled.opml"]
    assert len(feeds) == 1
    assert feeds[0].source_id == "enabled_source"
