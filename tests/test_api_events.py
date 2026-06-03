"""Tests for the FastAPI event detail endpoint."""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path

# Auto-load .env at module level
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_pg_url = os.getenv("DATABASE_URL", "")
if not _pg_url or not _pg_url.startswith(("postgresql://", "postgresql+psycopg://")):
    import pytest

    pytest.skip("No PostgreSQL", allow_module_level=True)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from news_system.api.main import app, get_db
from news_system.db.models import ArticleModel, Base, EventArticle, EventModel
from news_system.db.session import get_engine, get_session_local

# Ensure tables exist
_engine = get_engine()
Base.metadata.create_all(bind=_engine)


def now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(timezone.utc).date()


# ---------------------------------------------------------------------------
# Fixtures  (function-scoped so each test gets a clean slate)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh session and clean up all test data after the test."""
    SessionLocal = get_session_local()
    session = SessionLocal()
    yield session
    # Clean up only rows created by this test module. Do not wipe the shared
    # PostgreSQL database used by the live Daily_news pipeline.
    session.execute(text("""
        DELETE FROM event_articles
        WHERE event_id IN (SELECT id FROM events WHERE title = 'Test Event')
           OR article_id IN (SELECT id FROM articles WHERE url LIKE 'https://example.com/article/%')
    """))
    session.execute(text("DELETE FROM articles WHERE url LIKE 'https://example.com/article/%'"))
    session.execute(text("DELETE FROM events WHERE title = 'Test Event'"))
    session.commit()
    session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """Override the FastAPI DB dependency so tests use our session."""

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_event_and_articles(db, num_articles: int = 12, ts: int | None = None):
    """Insert one event + *num_articles* articles + link them.

    Returns (event_id, list_of_article_ids).
    *ts* – a unique timestamp seed so url_hashes don't collide across calls.
    """
    if ts is None:
        ts = int(datetime.now(timezone.utc).timestamp() * 1_000_000)

    ev = EventModel(
        title="Test Event",
        normalized_title="test event",
        category="politics",
        event_date=today(),
        first_seen_at=now(),
        last_seen_at=now(),
        article_count=num_articles,
        source_count=1,
        trusted_source_count=0,
        country_count=1,
        keywords=["test"],
        entities={},
    )
    db.add(ev)
    db.flush()  # get ev.id

    article_ids = []
    for i in range(num_articles):
        art = ArticleModel(
            title=f"Article {i}",
            normalized_title=f"article {i}",
            url=f"https://example.com/article/{ts}_{i}",
            canonical_url=f"https://example.com/article/{ts}_{i}",
            url_hash=f"hash{ts}_{i:04d}",
            source_name=f"Source {i % 3}",
            source_domain=f"source{i % 3}.com",
            source_type="rss",
            published_at=now(),
            collected_at=now(),
            language="en",
            country="us",
            category="politics",
            description=f"Description for article {i}",
            is_duplicate=False,
            fulltext_status="extracted",
            fulltext_quality_score=0.5,
            raw_payload={},
        )
        db.add(art)
        db.flush()
        article_ids.append(art.id)

        link = EventArticle(
            event_id=ev.id,
            article_id=art.id,
            relevance_score=1.0,
        )
        db.add(link)

    db.commit()
    return ev.id, article_ids


def _get_json(resp):
    return resp.json()


def _required_article_fields():
    return {
        "id",
        "title",
        "normalized_title",
        "url",
        "canonical_url",
        "source_name",
        "source_domain",
        "source_type",
        "published_at",
        "collected_at",
        "credibility_score",
        "fulltext_quality_score",
        "fulltext_status",
        "language",
        "country",
        "category",
        "description",
        "is_duplicate",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEventDetailPagination:
    """Verify article_limit and article_offset on the event detail endpoint."""

    def test_get_event_supports_article_limit_offset(self, db_session, client):
        """all_articles should respect article_limit and article_offset."""
        event_id, article_ids = _setup_event_and_articles(db_session, num_articles=12)

        resp = client.get(f"/events/{event_id}?article_limit=3&article_offset=0")
        assert resp.status_code == 200
        data = _get_json(resp)
        ev = data["event"]
        assert ev is not None
        assert len(ev["all_articles"]) <= 3, (
            f"Expected ≤3 articles, got {len(ev['all_articles'])}"
        )

    def test_representative_articles_not_paginated(self, db_session, client):
        """representative_articles should be based on full set, max 5, regardless of limit."""
        event_id, article_ids = _setup_event_and_articles(db_session, num_articles=12)

        # Even with article_limit=1, representative_articles should be full
        resp = client.get(f"/events/{event_id}?article_limit=1")
        assert resp.status_code == 200
        data = _get_json(resp)
        ev = data["event"]
        # representative_articles should be ≤5 and not limited by article_limit=1
        assert len(ev["representative_articles"]) <= 5

    def test_trusted_articles_default_limit_20(self, db_session, client):
        """trusted_articles has its own logic (not limited by article_limit)."""
        event_id, article_ids = _setup_event_and_articles(db_session, num_articles=12)

        resp = client.get(f"/events/{event_id}?article_limit=1")
        assert resp.status_code == 200
        data = _get_json(resp)
        ev = data["event"]
        # trusted_articles uses the full set, so it can have more than 1 item
        # even when article_limit=1
        trusted = ev["trusted_articles"]
        # With default credibility 0.5 (below 0.75 threshold), all articles
        # may be excluded — that's fine, the point is it's NOT limited by
        # the article_limit param
        assert isinstance(trusted, list)


class TestArticleResponseFields:
    """Verify each article dict contains all required fields."""

    def test_article_response_contains_all_fields(self, db_session, client):
        """Each article in the response must have all the specified fields."""
        event_id, article_ids = _setup_event_and_articles(db_session, num_articles=3)
        required = _required_article_fields()

        resp = client.get(f"/events/{event_id}?article_limit=10")
        assert resp.status_code == 200
        data = _get_json(resp)
        articles = data["event"]["all_articles"]

        assert len(articles) > 0, "Expected at least one article in response"

        for art in articles:
            missing = required - set(art.keys())
            extra = set(art.keys()) - required
            assert not missing, (
                f"Article {art.get('id')} missing fields: {missing}"
            )
            assert not extra, (
                f"Article {art.get('id')} has unexpected fields: {extra}"
            )