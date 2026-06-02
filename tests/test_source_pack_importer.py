from __future__ import annotations

from pathlib import Path

from news_feed_bootstrap.source_pack_importer import load_source_pack, merge_source_packs


def test_merge_source_packs_deduplicates_by_canonical_feed_url_and_prefers_https(tmp_path: Path) -> None:
    existing = tmp_path / "seed_sources.yaml"
    existing.write_text(
        """
seed_sources:
  - id: existing_http
    name: Existing HTTP
    type: rss
    enabled: false
    feed_url: http://example.com/rss.xml
    homepage: http://example.com
    publisher: Example Publisher
""",
        encoding="utf-8",
    )

    pack_a = tmp_path / "pack_a.yaml"
    pack_a.write_text(
        """
seed_sources:
  - id: duplicate_https
    name: Duplicate HTTPS
    type: rss
    enabled: true
    feed_url: https://example.com/rss.xml
    homepage: https://example.com/news
    publisher: Example Publisher A
  - id: unique_section_a
    name: Business Section
    type: rss
    enabled: true
    feed_url: https://example.com/business/rss.xml
    homepage: https://example.com
    publisher: Example Publisher
""",
        encoding="utf-8",
    )

    pack_b = tmp_path / "pack_b.yaml"
    pack_b.write_text(
        """
seed_sources:
  - id: duplicate_http
    name: Duplicate HTTP
    type: rss
    enabled: true
    feed_url: http://example.com/rss.xml
    homepage: http://example.com/news
    publisher: Example Publisher B
  - id: unique_section_b
    name: Politics Section
    type: rss
    enabled: true
    feed_url: https://example.com/politics/rss.xml
    homepage: https://example.com
    publisher: Example Publisher
  - id: google_news_reuters
    name: Reuters via Google News RSS
    type: google_news_rss
    enabled: true
    feed_url: https://news.google.com/rss/search?q=when:2d%20site:reuters.com&hl=en-US&gl=US&ceid=US:en
    publisher: Reuters
    dedupe_group: reuters
  - id: google_news_ap
    name: AP via Google News RSS
    type: google_news_rss
    enabled: true
    feed_url: https://news.google.com/rss/search?q=when:2d%20site:apnews.com&hl=en-US&gl=US&ceid=US:en
    publisher: AP
    dedupe_group: ap
  - id: grouped_pack
    name: Grouped Pack
    type: rss
    enabled: true
    dedupe_group: bundle_1
    sources:
      - feed_url: https://example.org/section-a.xml
        homepage: https://example.org/a
        publisher: Org A
      - feed_url: https://example.org/section-b.xml
        homepage: https://example.org/b
        publisher: Org B
""",
        encoding="utf-8",
    )

    merged = merge_source_packs([pack_a, pack_b], existing_config_path=existing, output_path=tmp_path / "merged.yaml")

    assert len(merged) == 7
    feed_urls = [row["feed_url"] for row in merged]
    assert "https://example.com/rss.xml" in feed_urls
    assert "https://example.com/business/rss.xml" in feed_urls
    assert "https://example.com/politics/rss.xml" in feed_urls
    assert "https://news.google.com/rss/search?q=when:2d%20site:reuters.com&hl=en-US&gl=US&ceid=US:en" in feed_urls
    assert "https://news.google.com/rss/search?q=when:2d%20site:apnews.com&hl=en-US&gl=US&ceid=US:en" in feed_urls
    assert "https://example.org/section-a.xml" in feed_urls
    assert "https://example.org/section-b.xml" in feed_urls

    https_row = next(row for row in merged if row["feed_url"] == "https://example.com/rss.xml")
    assert https_row["homepage"] == "https://example.com/news"
    assert https_row["enabled"] is True
    assert not any(row["feed_url"] == "http://example.com/rss.xml" for row in merged)

    assert any(row["feed_url"] == "https://example.com/business/rss.xml" and row["publisher"] == "Example Publisher" for row in merged)
    assert any(row["feed_url"] == "https://example.com/politics/rss.xml" and row["publisher"] == "Example Publisher" for row in merged)


def test_load_source_pack_expands_nested_sources(tmp_path: Path) -> None:
    pack = tmp_path / "pack.yaml"
    pack.write_text(
        """
seed_sources:
  - id: bundle
    name: Bundle
    type: rss
    enabled: true
    dedupe_group: bundle_1
    sources:
      - feed_url: http://example.org/a.xml
        homepage: http://example.org/a
        publisher: A
      - feed_url: https://example.org/b.xml
        homepage: https://example.org/b
        publisher: B
""",
        encoding="utf-8",
    )

    rows = load_source_pack(pack)
    assert [row["feed_url"] for row in rows] == ["http://example.org/a.xml", "https://example.org/b.xml"]
    assert all(row["dedupe_group"] == "bundle_1" for row in rows)


def test_load_source_pack_accepts_sources_key(tmp_path: Path) -> None:
    pack = tmp_path / "pack.yaml"
    pack.write_text(
        """
sources:
  - name: Example
    feed_url: https://example.com/rss.xml
    enabled: false
""",
        encoding="utf-8",
    )

    rows = load_source_pack(pack)
    assert len(rows) == 1
    assert rows[0]["feed_url"] == "https://example.com/rss.xml"
    assert rows[0]["enabled"] is False
