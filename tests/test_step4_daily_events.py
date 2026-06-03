from __future__ import annotations

import json
import os
import subprocess
import sys
import inspect
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from news_system.db.models import Base, ArticleModel, EventArticle, EventModel
from news_system.jobs import daily_event_job
from news_system.storage.repositories import ArticleRepository, EventRepository


def make_session(url="sqlite:///:memory:"):
    if url == "sqlite:///:memory:":
        engine = create_engine(url, future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    else:
        engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)(), engine


def add_article(db, title, url, source, *, hours_ago=1, duplicate=False, keywords=None, entities=None):
    article = ArticleModel(
        title=title,
        description=title,
        content_snippet=title,
        url=url,
        source_name=source,
        source_domain=f"{source.lower()}.example",
        source_type="rss",
        published_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        is_duplicate=duplicate,
        raw_payload={"keywords": keywords or [], "entities": entities or []},
    )
    ArticleRepository(db).add(article)
    db.commit()
    return article


def seed_articles(db):
    a1 = add_article(db, "Major earthquake strikes City Alpha", "https://a.example/1", "A", keywords=["earthquake", "alpha"], entities=["City Alpha"])
    a2 = add_article(db, "City Alpha hit by major earthquake", "https://b.example/2", "B", keywords=["earthquake", "alpha"], entities=["City Alpha"])
    dup = add_article(db, "Major earthquake strikes City Alpha duplicate", "https://dup.example/3", "Dup", duplicate=True, keywords=["earthquake", "alpha"], entities=["City Alpha"])
    other = add_article(db, "Tech company releases new product", "https://c.example/4", "C", keywords=["tech", "product"], entities=["TechCo"])
    old = add_article(db, "Old earthquake outside window", "https://old.example/5", "Old", hours_ago=48, keywords=["earthquake"], entities=["City Alpha"])
    return a1, a2, dup, other, old


def test_daily_event_job_public_signature_defaults_and_positional_args():
    sig = inspect.signature(daily_event_job)
    assert sig.parameters["lookback_hours"].default == 24
    assert sig.parameters["limit"].default == 10
    assert sig.parameters["articles"].kind is inspect.Parameter.KEYWORD_ONLY

    db, _ = make_session()
    seed_articles(db)

    # Public positional usage must bind as (db, lookback_hours, limit), not as
    # (db, articles, lookback_hours).
    events = daily_event_job(db, 24, 10)

    assert len(events) >= 2


def test_daily_event_job_builds_persists_links_and_excludes_duplicates():
    db, _ = make_session()
    a1, a2, dup, other, old = seed_articles(db)

    events = daily_event_job(db, lookback_hours=24, limit=10)

    assert len(events) >= 2
    persisted = EventRepository(db).list_daily(datetime.now(timezone.utc), limit=10)
    assert len(persisted) == len(events)
    top = persisted[0]
    assert top.final_score is not None
    assert top.article_count == 2
    assert top.source_count == 2
    links = db.execute(select(EventArticle).where(EventArticle.event_id == top.id)).scalars().all()
    linked_ids = {link.article_id for link in links}
    assert linked_ids == {a1.id, a2.id}
    assert dup.id not in linked_ids
    assert old.id not in linked_ids


def test_daily_event_job_rerun_upserts_without_duplicate_events_or_links():
    db, _ = make_session()
    seed_articles(db)

    first = daily_event_job(db, lookback_hours=24, limit=10)
    first_event_count = db.scalar(select(func.count()).select_from(EventModel))
    first_link_count = db.scalar(select(func.count()).select_from(EventArticle))
    second = daily_event_job(db, lookback_hours=24, limit=10)

    assert len(second) == len(first)
    assert db.scalar(select(func.count()).select_from(EventModel)) == first_event_count
    assert db.scalar(select(func.count()).select_from(EventArticle)) == first_link_count


def test_cli_build_events_and_show_daily_query_persisted_events(tmp_path):
    db_path = tmp_path / "daily.db"
    db, engine = make_session(f"sqlite:///{db_path}")
    seed_articles(db)
    db.close()
    engine.dispose()

    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}", "PYTHONPATH": "src"}
    build = subprocess.run([sys.executable, "-m", "news_system.cli", "build-events", "--lookback-hours", "24", "--limit", "10"], cwd="/opt/data/plugins/Daily_news", env=env, text=True, capture_output=True, check=True)
    build_payload = json.loads(build.stdout)
    assert build_payload["count"] >= 2
    assert build_payload["events"][0]["article_count"] == 2

    today = datetime.now(timezone.utc).date().isoformat()
    show = subprocess.run([sys.executable, "-m", "news_system.cli", "show-daily", "--date", today, "--limit", "10"], cwd="/opt/data/plugins/Daily_news", env=env, text=True, capture_output=True, check=True)
    show_payload = json.loads(show.stdout)
    assert show_payload["date"] == today
    assert show_payload["count"] == build_payload["count"]
    assert show_payload["events"][0]["article_count"] == 2


def test_api_daily_route_returns_persisted_events():
    from fastapi.testclient import TestClient
    from news_system.api import main as api_main

    db, _ = make_session()
    seed_articles(db)
    daily_event_job(db, lookback_hours=24, limit=10)

    def override_db():
        try:
            yield db
        finally:
            pass

    api_main.app.dependency_overrides[api_main.get_db] = override_db
    try:
        client = TestClient(api_main.app)
        today = datetime.now(timezone.utc).date().isoformat()
        resp = client.get(f"/events/daily?date={today}&limit=10")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["date"] == today
        assert payload["count"] >= 2
        assert payload["events"][0]["article_count"] == 2
    finally:
        api_main.app.dependency_overrides.clear()
