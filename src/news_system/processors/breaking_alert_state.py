"""Breaking alert state management with cooldown and major update detection."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from news_system.db.models import BreakingAlertState, EventModel
from news_system.processors.scorer import CATEGORY_IMPORTANCE


COOLDOWN_MINUTES = 60
SCORE_THRESHOLD = 0.15
SOURCE_THRESHOLD = 2
ARTICLE_THRESHOLD = 5
HIGH_SEVERITY = {"war_conflict", "disaster", "economy", "health", "cybersecurity"}


def can_alert(event: EventModel, db: Session) -> tuple[bool, str]:
    """
    Check if an event is eligible for alerting.
    Returns (can_alert, reason).
    """
    now = datetime.now(timezone.utc)

    # Fetch or create alert state
    state = db.execute(
        select(BreakingAlertState).where(
            BreakingAlertState.event_id == event.id,
            BreakingAlertState.status == "active",
        )
    ).scalar_one_or_none()

    if state is None:
        return (True, "new_event")

    # Cooldown check
    if state.last_alerted_at:
        last_alerted = state.last_alerted_at
        if last_alerted.tzinfo is None:
            last_alerted = last_alerted.replace(tzinfo=timezone.utc)
        elapsed = (now - last_alerted).total_seconds() / 60
        if elapsed < COOLDOWN_MINUTES:
            # Check major update conditions
            reasons = []
            bs = getattr(event, "breaking_score", 0.0) or 0.0
            if bs - state.last_breaking_score >= SCORE_THRESHOLD:
                reasons.append(f"breaking_score +{bs - state.last_breaking_score:.2f}")
            trusted = getattr(event, "trusted_source_count", 0) or 0
            if trusted - state.last_trusted_source_count >= SOURCE_THRESHOLD:
                reasons.append(f"trusted_sources +{trusted - state.last_trusted_source_count}")
            articles = getattr(event, "article_count", 0) or 0
            if articles - state.last_article_count >= ARTICLE_THRESHOLD:
                reasons.append(f"articles +{articles - state.last_article_count}")

            # Category upgrade check
            cat = getattr(event, "category", None)
            if cat and cat in HIGH_SEVERITY:
                reasons.append(f"high_severity_category:{cat}")

            if reasons:
                return (True, "major_update:" + ";".join(reasons))
            return (False, f"cooldown_active:{COOLDOWN_MINUTES - int(elapsed)}m_remaining")

    return (True, "eligible")


def update_alert_state(event: EventModel, db: Session) -> BreakingAlertState:
    """
    Update or create breaking alert state for an event.
    """
    now = datetime.now(timezone.utc)

    state = db.execute(
        select(BreakingAlertState).where(
            BreakingAlertState.event_id == event.id,
            BreakingAlertState.status == "active",
        )
    ).scalar_one_or_none()

    bs = getattr(event, "breaking_score", 0.0) or 0.0
    trusted = getattr(event, "trusted_source_count", 0) or 0
    articles = getattr(event, "article_count", 0) or 0

    if state is None:
        state = BreakingAlertState(
            event_id=event.id,
            first_detected_at=now,
            last_detected_at=now,
            last_alerted_at=now,
            alert_count=1,
            last_breaking_score=bs,
            max_breaking_score=bs,
            last_trusted_source_count=trusted,
            last_article_count=articles,
            status="active",
        )
        db.add(state)
    else:
        state.last_detected_at = now
        state.last_alerted_at = now
        state.alert_count += 1
        state.last_breaking_score = bs
        state.max_breaking_score = max(state.max_breaking_score, bs)
        state.last_trusted_source_count = trusted
        state.last_article_count = articles
        state.status = "active"
        db.flush()

    return state