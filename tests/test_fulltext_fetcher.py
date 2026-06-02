from __future__ import annotations

from pathlib import Path

from news_feed_bootstrap.fulltext_fetcher import fetch_fulltext_candidates, run_fulltext_fetch


class DummyClient:
    pass


def test_fetch_fulltext_prefers_article_page_over_rss_content(monkeypatch) -> None:
    monkeypatch.setattr("news_feed_bootstrap.fulltext_fetcher.fetch_article_content", lambda url, client=None: {"fulltext": "Article body text"})
    rows = fetch_fulltext_candidates(
        [
            {
                "id": "1",
                "title": "Example",
                "url": "https://example.com/article",
                "content": "RSS summary text",
                "fetch_required": True,
            }
        ]
    )

    assert rows[0]["fulltext"] == "Article body text"
    assert rows[0]["fulltext_status"] == "success"
    assert rows[0]["fulltext_source"] == "http_fallback"
    assert rows[0]["fetch_reason"] == "http_extracted_fulltext"


def test_fetch_fulltext_falls_back_to_rss_content_when_http_empty(monkeypatch) -> None:
    monkeypatch.setattr("news_feed_bootstrap.fulltext_fetcher.fetch_article_content", lambda url, client=None: {"fulltext": ""})
    rows = fetch_fulltext_candidates(
        [
            {
                "id": "1",
                "title": "Example",
                "url": "https://example.com/article",
                "content": "RSS summary text",
                "fetch_required": True,
            }
        ]
    )

    assert rows[0]["fulltext"] == "RSS summary text"
    assert rows[0]["fulltext_status"] == "partial"
    assert rows[0]["fulltext_source"] == "rss_feed_content"
    assert rows[0]["fetch_reason"] == "rss_content_only"


def test_fetch_fulltext_candidates_reuses_one_client(monkeypatch) -> None:
    client = DummyClient()
    seen_clients: list[object] = []

    def fake_fetch(url: str, client=None):
        seen_clients.append(client)
        return {"fulltext": url}

    monkeypatch.setattr("news_feed_bootstrap.fulltext_fetcher.fetch_article_content", fake_fetch)
    rows = fetch_fulltext_candidates(
        [
            {"id": "1", "title": "A", "url": "https://example.com/a", "fetch_required": True},
            {"id": "2", "title": "B", "url": "https://example.com/b", "fetch_required": True},
        ],
        client=client,
    )

    assert seen_clients == [client, client]
    assert rows[0]["fulltext"] == "https://example.com/a"
    assert rows[1]["fulltext"] == "https://example.com/b"


def test_fetch_fulltext_candidates_supports_chunked_parallel_processing(monkeypatch) -> None:
    seen: list[str] = []

    def fake_fetch(url: str, client=None):
        seen.append(url)
        return {"fulltext": url}

    monkeypatch.setattr("news_feed_bootstrap.fulltext_fetcher.fetch_article_content", fake_fetch)
    rows = fetch_fulltext_candidates(
        [
            {"id": "1", "title": "A", "url": "https://example.com/a", "fetch_required": True},
            {"id": "2", "title": "B", "url": "https://example.com/b", "fetch_required": True},
            {"id": "3", "title": "C", "url": "https://example.com/c", "fetch_required": True},
        ],
        chunk_size=2,
        max_workers=2,
    )

    assert seen == ["https://example.com/a", "https://example.com/b", "https://example.com/c"]
    assert [row["fulltext"] for row in rows] == ["https://example.com/a", "https://example.com/b", "https://example.com/c"]


def test_run_fulltext_fetch_writes_output(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "labels.jsonl"
    output_path = tmp_path / "fulltext.jsonl"
    input_path.write_text(
        '{"id":"1","title":"Example","url":"https://example.com/article","fetch_required":false}\n',
        encoding="utf-8",
    )

    rows = run_fulltext_fetch(str(input_path), str(output_path))

    assert rows[0]["fulltext_status"] == "skipped"
    assert output_path.exists()
    assert '"fulltext_status": "skipped"' in output_path.read_text(encoding="utf-8")
