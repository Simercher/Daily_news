from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from news_system.db.models import ArticleModel, Base
from news_system.storage.repositories import ArticleRepository


def make_session(url="sqlite:///:memory:"):
    if url == "sqlite:///:memory:":
        engine = create_engine(url, future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)(), engine


def add_article(
    db,
    title,
    url,
    *,
    source="Wire",
    category="world",
    hours_ago=1,
    description=None,
    content=None,
    published_at=None,
    is_duplicate=False,
):
    article = ArticleModel(
        title=title,
        description=description,
        content_snippet=content,
        url=url,
        source_name=source,
        source_domain=f"{source.lower()}.example",
        source_type="rss",
        category=category,
        published_at=published_at or (datetime.now(timezone.utc) - timedelta(hours=hours_ago)),
        raw_payload={"source_config": {"name": source, "trusted": True}},
        is_duplicate=is_duplicate,
    )
    ArticleRepository(db).add(article)
    db.commit()
    return article


def test_article_repository_search_matches_title_description_and_content_with_limit_and_filters():
    db, _ = make_session()
    title_hit = add_article(db, "Climate summit reaches agreement", "https://example.com/title", source="Reuters", category="climate", hours_ago=1)
    description_hit = add_article(db, "Markets open higher", "https://example.com/desc", description="Investors discuss climate risk", source="AP", category="business", hours_ago=2)
    content_hit = add_article(db, "Policy briefing", "https://example.com/content", content="A deep climate transition analysis", source="Reuters", category="analysis", hours_ago=3)
    add_article(db, "Climate archive", "https://example.com/old", source="Reuters", category="climate", hours_ago=72)

    results = ArticleRepository(db).search("climate", limit=2, lookback_hours=24)

    assert len(results) == 2
    assert title_hit in results
    assert description_hit in results
    assert content_hit not in results

    filtered = ArticleRepository(db).search("climate", source="Reuters", category="analysis", lookback_hours=24)
    assert [article.id for article in filtered] == [content_hit.id]


def test_article_repository_search_uses_stable_id_tiebreaker_for_same_timestamp():
    db, _ = make_session()
    published_at = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)
    older_id = add_article(db, "Climate policy update", "https://example.com/older", content="climate", published_at=published_at)
    newer_id = add_article(db, "Climate policy update follow-up", "https://example.com/newer", content="climate", published_at=published_at)

    results = ArticleRepository(db).search("climate", lookback_hours=24, limit=10)

    assert [article.id for article in results[:2]] == [newer_id.id, older_id.id]


def test_article_repository_search_excludes_duplicates_by_default_and_includes_them_when_requested():
    db, _ = make_session()
    unique_article = add_article(db, "Climate market outlook", "https://example.com/unique", content="climate")
    duplicate_article = add_article(
        db,
        "Climate market outlook duplicate",
        "https://example.com/duplicate",
        content="climate",
        is_duplicate=True,
    )

    default_results = ArticleRepository(db).search("climate", lookback_hours=24, limit=10)
    include_duplicate_results = ArticleRepository(db).search(
        "climate",
        lookback_hours=24,
        limit=10,
        include_duplicates=True,
    )

    assert [article.id for article in default_results] == [unique_article.id]
    assert [article.id for article in include_duplicate_results] == [duplicate_article.id, unique_article.id]


def test_cli_search_outputs_json_and_empty_result_for_filter(tmp_path):
    db_path = tmp_path / "search.db"
    db, engine = make_session(f"sqlite:///{db_path}")
    article = add_article(
        db,
        "Mars mission launch window opens",
        "https://space.example/mars",
        source="SpaceWire",
        category="science",
        description="Mission planners prepare the spacecraft",
    )
    article_id = article.id
    db.close()
    engine.dispose()

    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "PYTHONPATH": "src"}
    hit = subprocess.run(
        [sys.executable, "-m", "news_system.cli", "search", "mars", "--lookback-hours", "24", "--limit", "5"],
        cwd="/opt/data/plugins/Daily_news",
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    payload = json.loads(hit.stdout)
    assert payload["cmd"] == "search"
    assert payload["query"] == "mars"
    assert payload["lookback_hours"] == 24
    assert payload["limit"] == 5
    assert payload["count"] == 1
    assert payload["articles"][0]["id"] == article_id
    assert payload["articles"][0]["title"] == "Mars mission launch window opens"
    assert payload["articles"][0]["source_name"] == "SpaceWire"
    assert payload["articles"][0]["url"] == "https://space.example/mars"
    assert payload["articles"][0]["description"] == "Mission planners prepare the spacecraft"

    miss = subprocess.run(
        [sys.executable, "-m", "news_system.cli", "search", "mars", "--source", "OtherWire", "--lookback-hours", "24"],
        cwd="/opt/data/plugins/Daily_news",
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    miss_payload = json.loads(miss.stdout)
    assert miss_payload["count"] == 0
    assert miss_payload["articles"] == []
    assert miss_payload["source"] == "OtherWire"


def test_cli_search_rejects_invalid_limit_lookback_and_blank_query(tmp_path):
    db_path = tmp_path / "search_validation.db"
    db, engine = make_session(f"sqlite:///{db_path}")
    add_article(db, "Valid article", "https://example.com/valid", description="query text")
    db.close()
    engine.dispose()

    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "PYTHONPATH": "src"}

    invalid_limit = subprocess.run(
        [sys.executable, "-m", "news_system.cli", "search", "query", "--limit", "0"],
        cwd="/opt/data/plugins/Daily_news",
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(invalid_limit.stdout) == {"cmd": "search", "error": "--limit must be a positive integer"}

    invalid_lookback = subprocess.run(
        [sys.executable, "-m", "news_system.cli", "search", "query", "--lookback-hours", "-1"],
        cwd="/opt/data/plugins/Daily_news",
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(invalid_lookback.stdout) == {"cmd": "search", "error": "--lookback-hours must be zero or greater"}

    blank_query = subprocess.run(
        [sys.executable, "-m", "news_system.cli", "search", "   "],
        cwd="/opt/data/plugins/Daily_news",
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(blank_query.stdout) == {"cmd": "search", "error": "query must not be blank"}
