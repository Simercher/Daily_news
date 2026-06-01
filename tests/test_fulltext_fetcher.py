from __future__ import annotations

from pathlib import Path

from news_feed_bootstrap.fulltext_fetcher import fetch_fulltext_candidates, run_fulltext_fetch


class DummyClient:
    pass


def test_fetch_fulltext_prefers_rss_content_when_mcp_unavailable(monkeypatch) -> None:
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
