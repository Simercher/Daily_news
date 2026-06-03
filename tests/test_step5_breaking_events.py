from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from news_system.db.models import ArticleModel, Base, EventArticle, EventModel
from news_system.jobs import breaking_watch_job
from news_system.storage.repositories import ArticleRepository, EventRepository


def make_session(url="sqlite:///:memory:"):
    if url == "sqlite:///:memory:":
        engine = create_engine(url, future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)(), engine


def add_article(db, title, url, source, *, minutes_ago=10, duplicate=False, category="disaster", trusted=True, keywords=None, entities=None):
    article = ArticleModel(
        title=title,
        description=title,
        content_snippet=title,
        url=url,
        source_name=source,
        source_domain=f"{source.lower()}.example",
        source_type="rss",
        category=category,
        country="US",
        published_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        is_duplicate=duplicate,
        raw_payload={
            "keywords": keywords or ["earthquake", "emergency"],
            "entities": entities or ["City Alpha"],
            "source_config": {"trusted": trusted, "name": source},
        },
    )
    ArticleRepository(db).add(article)
    db.commit()
    return article


def seed_breaking(db):
    return [
        add_article(db, "Major earthquake strikes City Alpha", "https://a.example/1", "TrustedA"),
        add_article(db, "City Alpha hit by major earthquake", "https://b.example/2", "TrustedB", minutes_ago=12),
        add_article(db, "Powerful earthquake emergency in City Alpha", "https://c.example/3", "TrustedC", minutes_ago=14),
    ]


def test_breaking_watch_job_persists_breaking_event_with_scores_metadata_and_links():
    db, _ = make_session()
    articles = seed_breaking(db)

    events = breaking_watch_job(db, since_minutes=60, limit=20)

    assert len(events) >= 1
    event = events[0]
    assert event.is_breaking is True
    assert event.breaking_detected_at is not None
    assert event.trusted_source_count >= 2
    assert event.article_count == 3
    assert event.category == "disaster"
    assert event.breaking_score >= 0.75
    links = db.execute(select(EventArticle).where(EventArticle.event_id == event.id)).scalars().all()
    assert {link.article_id for link in links} == {a.id for a in articles}


def test_breaking_watch_job_rerun_is_idempotent_for_events_and_links():
    db, _ = make_session()
    seed_breaking(db)

    first = breaking_watch_job(db, since_minutes=60, limit=20)
    first_event_count = db.scalar(select(func.count()).select_from(EventModel))
    first_link_count = db.scalar(select(func.count()).select_from(EventArticle))
    second = breaking_watch_job(db, since_minutes=60, limit=20)

    assert [e.id for e in second] == [e.id for e in first]
    assert db.scalar(select(func.count()).select_from(EventModel)) == first_event_count
    assert db.scalar(select(func.count()).select_from(EventArticle)) == first_link_count


def test_breaking_watch_job_does_not_persist_low_severity_untrusted_single_article():
    db, _ = make_session()
    add_article(db, "Routine product update from company", "https://low.example/1", "Untrusted", category="technology", trusted=False, keywords=["product"], entities=["Company"])

    events = breaking_watch_job(db, since_minutes=60, limit=20)

    assert events == []
    assert db.scalar(select(func.count()).select_from(EventModel)) == 0


def test_cli_watch_breaking_and_show_breaking_output_json(tmp_path):
    db_path = tmp_path / "breaking.db"
    db, engine = make_session(f"sqlite:///{db_path}")
    seed_breaking(db)
    db.close(); engine.dispose()

    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "PYTHONPATH": "src"}
    watch = subprocess.run([sys.executable, "-m", "news_system.cli", "watch-breaking", "--lookback-minutes", "60", "--limit", "20"], cwd="/opt/data/plugins/Daily_news", env=env, text=True, capture_output=True, check=True)
    watch_payload = json.loads(watch.stdout)
    assert watch_payload["lookback_minutes"] == 60
    assert watch_payload["limit"] == 20
    assert watch_payload["count"] >= 1
    assert watch_payload["events"][0]["is_breaking"] is True

    show = subprocess.run([sys.executable, "-m", "news_system.cli", "show-breaking", "--since-minutes", "180", "--limit", "20"], cwd="/opt/data/plugins/Daily_news", env=env, text=True, capture_output=True, check=True)
    show_payload = json.loads(show.stdout)
    assert show_payload["since_minutes"] == 180
    assert show_payload["limit"] == 20
    assert show_payload["count"] == watch_payload["count"]
    assert show_payload["events"][0]["is_breaking"] is True


def test_api_breaking_route_returns_persisted_breaking_events():
    from fastapi.testclient import TestClient
    from news_system.api import main as api_main

    db, _ = make_session()
    seed_breaking(db)
    breaking_watch_job(db, since_minutes=60, limit=20)

    def override_db():
        yield db

    api_main.app.dependency_overrides[api_main.get_db] = override_db
    try:
        client = TestClient(api_main.app)
        resp = client.get("/events/breaking?since_minutes=180&limit=20")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["since_minutes"] == 180
        assert payload["count"] >= 1
        assert payload["events"][0]["is_breaking"] is True
    finally:
        api_main.app.dependency_overrides.clear()
