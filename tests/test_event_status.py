"""Tests for EventModel status enum (PostgreSQL)."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Load .env BEFORE importing anything from news_system
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from news_system.db.models import Base, EventModel

# ── Module-level skip if no PostgreSQL ──────────────────────────────
_pg_url = os.getenv("DATABASE_URL", "")
_no_pg = not _pg_url or not _pg_url.startswith(("postgresql://", "postgresql+psycopg://"))
if _no_pg:
    pytest.skip("DATABASE_URL not set or not PostgreSQL; skipping tests", allow_module_level=True)


# ── Fixtures ─────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def engine():
    """One engine per module — feeds into session fixtures."""
    e = create_engine(_pg_url, future=True)
    Base.metadata.create_all(e)
    yield e
    Base.metadata.drop_all(e)
    e.dispose()


@pytest.fixture
def db_session(engine):
    """Per-test transactional session with rollback."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, future=True)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ── Tests ────────────────────────────────────────────────────────────
class TestEventStatusDefaults:
    """EventModel.status defaults to 'active'."""

    def test_events_status_defaults_to_active(self, db_session):
        """Column default 'active' is applied on INSERT."""
        event = EventModel(
            title="Default Status Event",
            event_date=datetime.now(timezone.utc).date(),
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        assert event.status == "active"


class TestEventStatusSupportsAllValues:
    """All valid status values should be accepted."""

    @pytest.mark.parametrize("status", ["breaking", "active", "archived", "merged", "ignored"])
    def test_events_status_supports_all_values(self, db_session, status):
        event = EventModel(
            title=f"Status-{status}",
            event_date=datetime.now(timezone.utc).date(),
            status=status,
        )
        db_session.add(event)
        db_session.commit()
        db_session.refresh(event)
        assert event.status == status


class TestMergeEvents:
    """Merge logic: marking source event status and recording merged_into_event_id."""

    def test_merge_events_sets_source_status_merged(self, db_session):
        target = EventModel(
            title="Target Event",
            event_date=datetime.now(timezone.utc).date(),
            status="active",
        )
        source = EventModel(
            title="Source Event",
            event_date=datetime.now(timezone.utc).date(),
            status="active",
        )
        db_session.add_all([target, source])
        db_session.commit()
        db_session.refresh(target)
        db_session.refresh(source)

        # Simulate merge: set source status to "merged"
        source.status = "merged"
        db_session.commit()
        db_session.refresh(source)

        assert source.status == "merged"
        # Target should remain unchanged
        db_session.refresh(target)
        assert target.status == "active"

    def test_merge_events_records_merged_into_event_id(self, db_session):
        target = EventModel(
            title="Target Event For Merge ID",
            event_date=datetime.now(timezone.utc).date(),
            status="active",
        )
        source = EventModel(
            title="Source Event For Merge ID",
            event_date=datetime.now(timezone.utc).date(),
            status="active",
        )
        db_session.add_all([target, source])
        db_session.commit()
        db_session.refresh(target)
        db_session.refresh(source)

        # Simulate merge: record the target event ID in the source's entities
        source.entities = {"merged_into_event_id": target.id}
        db_session.commit()
        db_session.refresh(source)

        assert source.entities.get("merged_into_event_id") == target.id
        # Also confirm target untouched
        db_session.refresh(target)
        assert target.entities.get("merged_into_event_id") is None