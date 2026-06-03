"""Tests for breaking alert state management (PostgreSQL)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from news_system.db.models import Base, BreakingAlertState, EventModel
from news_system.db.session import get_engine, get_session_local
from news_system.processors.breaking_alert_state import can_alert, update_alert_state


# Skip module if no PostgreSQL is configured
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_env_path):
    for line in open(_env_path).readlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_pg_url = os.getenv("DATABASE_URL", "")
_no_pg = not _pg_url or not _pg_url.startswith(("postgresql://", "postgresql+psycopg://"))
if _no_pg:
    pytest.skip("DATABASE_URL not set; skipping PostgreSQL tests", allow_module_level=True)


@pytest.fixture
def db_session():
    engine = get_engine()
    Base.metadata.create_all(engine)
    session = get_session_local()()
    yield session
    session.close()


@pytest.fixture
def sample_event(db_session):
    ev = EventModel(
        title="Test Event",
        event_date=datetime.now(timezone.utc).date(),
        status="active",
    )
    db_session.add(ev)
    db_session.commit()
    db_session.refresh(ev)
    return ev


class TestCanAlert:
    def test_new_event_no_state(self, sample_event, db_session):
        eligible, reason = can_alert(sample_event, db_session)
        assert eligible is True
        assert reason == "new_event"

    def test_after_cooldown_eligible(self, sample_event, db_session):
        state = BreakingAlertState(
            event_id=sample_event.id,
            first_detected_at=datetime.now(timezone.utc) - timedelta(hours=2),
            last_detected_at=datetime.now(timezone.utc) - timedelta(hours=2),
            last_alerted_at=datetime.now(timezone.utc) - timedelta(minutes=90),
            alert_count=1,
            last_breaking_score=0.5,
            max_breaking_score=0.5,
            last_trusted_source_count=1,
            last_article_count=1,
            status="active",
        )
        db_session.add(state)
        db_session.commit()

        eligible, reason = can_alert(sample_event, db_session)
        assert eligible is True

    def test_cooldown_active_no_major_update(self, sample_event, db_session):
        state = BreakingAlertState(
            event_id=sample_event.id,
            first_detected_at=datetime.now(timezone.utc),
            last_detected_at=datetime.now(timezone.utc),
            last_alerted_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            alert_count=1,
            last_breaking_score=0.5,
            max_breaking_score=0.5,
            last_trusted_source_count=1,
            last_article_count=1,
            status="active",
        )
        db_session.add(state)
        db_session.commit()

        eligible, reason = can_alert(sample_event, db_session)
        assert eligible is False
        assert "cooldown" in reason

    def test_major_update_breaking_score_increased(self, sample_event, db_session):
        state = BreakingAlertState(
            event_id=sample_event.id,
            first_detected_at=datetime.now(timezone.utc),
            last_detected_at=datetime.now(timezone.utc),
            last_alerted_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            alert_count=1,
            last_breaking_score=0.3,
            max_breaking_score=0.3,
            last_trusted_source_count=1,
            last_article_count=1,
            status="active",
        )
        db_session.add(state)
        db_session.commit()

        sample_event.breaking_score = 0.6
        sample_event.trusted_source_count = 1
        sample_event.article_count = 1

        eligible, reason = can_alert(sample_event, db_session)
        assert eligible is True
        assert "breaking_score" in reason

    def test_major_update_trusted_sources_increased(self, sample_event, db_session):
        state = BreakingAlertState(
            event_id=sample_event.id,
            first_detected_at=datetime.now(timezone.utc),
            last_detected_at=datetime.now(timezone.utc),
            last_alerted_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            alert_count=1,
            last_breaking_score=0.5,
            max_breaking_score=0.5,
            last_trusted_source_count=0,
            last_article_count=1,
            status="active",
        )
        db_session.add(state)
        db_session.commit()

        sample_event.breaking_score = 0.5
        sample_event.trusted_source_count = 2
        sample_event.article_count = 1

        eligible, reason = can_alert(sample_event, db_session)
        assert eligible is True
        assert "trusted_sources" in reason

    def test_major_update_articles_increased(self, sample_event, db_session):
        state = BreakingAlertState(
            event_id=sample_event.id,
            first_detected_at=datetime.now(timezone.utc),
            last_detected_at=datetime.now(timezone.utc),
            last_alerted_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            alert_count=1,
            last_breaking_score=0.5,
            max_breaking_score=0.5,
            last_trusted_source_count=1,
            last_article_count=2,
            status="active",
        )
        db_session.add(state)
        db_session.commit()

        sample_event.breaking_score = 0.5
        sample_event.trusted_source_count = 1
        sample_event.article_count = 7

        eligible, reason = can_alert(sample_event, db_session)
        assert eligible is True
        assert "articles" in reason

    def test_high_severity_category_breaks_cooldown(self, sample_event, db_session):
        state = BreakingAlertState(
            event_id=sample_event.id,
            first_detected_at=datetime.now(timezone.utc),
            last_detected_at=datetime.now(timezone.utc),
            last_alerted_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            alert_count=1,
            last_breaking_score=0.5,
            max_breaking_score=0.5,
            last_trusted_source_count=1,
            last_article_count=1,
            status="active",
        )
        db_session.add(state)
        db_session.commit()

        sample_event.breaking_score = 0.5
        sample_event.trusted_source_count = 1
        sample_event.article_count = 1
        sample_event.category = "war_conflict"

        eligible, reason = can_alert(sample_event, db_session)
        assert eligible is True
        assert "war_conflict" in reason


class TestUpdateAlertState:
    def test_creates_new_state(self, sample_event, db_session):
        state = update_alert_state(sample_event, db_session)
        assert state is not None
        assert state.event_id == sample_event.id
        assert state.alert_count == 1
        assert state.status == "active"

    def test_increments_alert_count(self, sample_event, db_session):
        state = update_alert_state(sample_event, db_session)
        assert state.alert_count == 1

        state2 = update_alert_state(sample_event, db_session)
        assert state2.id == state.id
        assert state2.alert_count == 2

    def test_updates_max_breaking_score(self, sample_event, db_session):
        sample_event.breaking_score = 0.5
        state = update_alert_state(sample_event, db_session)
        assert state.max_breaking_score == 0.5

        sample_event.breaking_score = 0.8
        state2 = update_alert_state(sample_event, db_session)
        assert state2.max_breaking_score == 0.8
        assert state2.last_breaking_score == 0.8

    def test_tracks_article_and_source_counts(self, sample_event, db_session):
        sample_event.article_count = 5
        sample_event.trusted_source_count = 3
        state = update_alert_state(sample_event, db_session)
        assert state.last_article_count == 5
        assert state.last_trusted_source_count == 3

    def test_persists_in_db(self, sample_event, db_session):
        state = update_alert_state(sample_event, db_session)
        db_session.commit()

        fetched = db_session.get(BreakingAlertState, state.id)
        assert fetched is not None
        assert fetched.event_id == sample_event.id