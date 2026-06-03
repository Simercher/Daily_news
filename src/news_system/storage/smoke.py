from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from news_system.db.session import get_session_local, get_engine

REQUIRED_TABLES = [
    "articles",
    "news_sources",
    "events",
    "event_articles",
    "collection_runs",
    "breaking_alert_states",
]


def run_db_smoke(db: Session | None = None) -> dict:
    """Run a small PostgreSQL persistence smoke check.

    The check verifies the required tables, inserts one source/article/event/link/run
    using unique values, and returns a JSON-serializable summary. Exceptions are not
    swallowed so callers/CLI/tests get a real failure and non-zero exit.
    """
    owns_session = db is None
    session = db or get_session_local()()
    suffix = uuid4().hex
    now = datetime.now(timezone.utc)

    try:
        inspector = inspect(get_engine() if owns_session else session.get_bind())
        existing_tables = set(inspector.get_table_names(schema="public"))
        missing_tables = [table for table in REQUIRED_TABLES if table not in existing_tables]
        if missing_tables:
            raise RuntimeError(f"Missing required DB tables: {', '.join(missing_tables)}")

        source_name = f"db-smoke-{suffix}"
        article_url = f"https://example.invalid/daily-news/db-smoke/{suffix}"
        article_hash = f"db-smoke-{suffix}"

        source_id = session.execute(
            text(
                """
                INSERT INTO news_sources
                    (source_type, name, domain, url, country, language, category,
                     trusted, enabled, priority, credibility_score, region,
                     ownership_type, source_notes, created_at, updated_at)
                VALUES
                    (:source_type, :name, :domain, :url, :country, :language, :category,
                     :trusted, :enabled, :priority, :credibility_score, :region,
                     :ownership_type, :source_notes, :now, :now)
                RETURNING id
                """
            ),
            {
                "source_type": "rss",
                "name": source_name,
                "domain": "example.invalid",
                "url": "https://example.invalid/rss.xml",
                "country": "WW",
                "language": "en",
                "category": "smoke",
                "trusted": True,
                "enabled": True,
                "priority": 1,
                "credibility_score": 0.95,
                "region": "global",
                "ownership_type": "test",
                "source_notes": "Inserted by daily-news db-smoke.",
                "now": now,
            },
        ).scalar_one()

        article_id = session.execute(
            text(
                """
                INSERT INTO articles
                    (external_id, source_type, source_name, source_domain, title,
                     normalized_title, description, content_snippet, url, canonical_url,
                     url_hash, language, country, category, published_at, collected_at,
                     raw_payload, title_hash, content_hash, is_duplicate,
                     fulltext_status, fulltext_quality_score, created_at, updated_at)
                VALUES
                    (:external_id, 'rss', :source_name, 'example.invalid', :title,
                     :normalized_title, :description, :content_snippet, :url, :canonical_url,
                     :url_hash, 'en', 'WW', 'smoke', :now, :now,
                     CAST(:raw_payload AS jsonb), :title_hash, :content_hash, FALSE,
                     'extracted', 0.8, :now, :now)
                RETURNING id
                """
            ),
            {
                "external_id": f"db-smoke-ext-{suffix}",
                "source_name": source_name,
                "title": f"Daily News DB smoke {suffix}",
                "normalized_title": "daily news db smoke",
                "description": "Inserted by daily-news db-smoke.",
                "content_snippet": "PostgreSQL smoke article.",
                "url": article_url,
                "canonical_url": article_url,
                "url_hash": article_hash,
                "raw_payload": '{"smoke": true}',
                "title_hash": f"title-{suffix}",
                "content_hash": f"content-{suffix}",
                "now": now,
            },
        ).scalar_one()

        event_id = session.execute(
            text(
                """
                INSERT INTO events
                    (title, normalized_title, category, severity, event_date,
                     first_seen_at, last_seen_at, article_count, source_count,
                     trusted_source_count, country_count, popular_score, importance_score,
                     breaking_score, final_score, status, is_breaking, breaking_detected_at,
                     keywords, entities, event_fingerprint, score_breakdown,
                     last_scored_at, cluster_method, created_at, updated_at)
                VALUES
                    (:title, :normalized_title, 'smoke', 'low', CURRENT_DATE,
                     :now, :now, 1, 1, 1, 1, 1.0, 1.0,
                     1.0, 1.0, 'active', TRUE, :now,
                     ARRAY['db-smoke']::TEXT[], CAST(:entities AS jsonb),
                     :event_fingerprint, CAST(:score_breakdown AS jsonb),
                     :now, 'db-smoke', :now, :now)
                RETURNING id
                """
            ),
            {
                "title": f"Daily News smoke event {suffix}",
                "normalized_title": "daily news smoke event",
                "entities": '{"smoke": true}',
                "event_fingerprint": f"smoke|{suffix}",
                "score_breakdown": '{"smoke": true}',
                "now": now,
            },
        ).scalar_one()

        session.execute(
            text(
                """
                INSERT INTO event_articles
                    (event_id, article_id, relevance_score, is_representative, created_at)
                VALUES (:event_id, :article_id, 1.0, TRUE, :now)
                """
            ),
            {"event_id": event_id, "article_id": article_id, "now": now},
        )

        collection_run_id = session.execute(
            text(
                """
                INSERT INTO collection_runs
                    (source_type, source_name, started_at, finished_at, status,
                     lookback_hours, fetched_count, inserted_count, duplicate_count,
                     error_count, error_message, metadata, created_at, updated_at)
                VALUES
                    ('rss', :source_name, :now, :now, 'success',
                     1, 1, 1, 0, 0, NULL, CAST(:metadata AS jsonb), :now, :now)
                RETURNING id
                """
            ),
            {"source_name": source_name, "metadata": '{"smoke": true}', "now": now},
        ).scalar_one()

        counts = session.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE event_date = CURRENT_DATE) AS daily_events,
                    COUNT(*) FILTER (WHERE is_breaking IS TRUE) AS breaking_events
                FROM events
                WHERE id = :event_id
                """
            ),
            {"event_id": event_id},
        ).mappings().one()

        session.commit()
        return {
            "ok": True,
            "tables": sorted(REQUIRED_TABLES),
            "suffix": suffix,
            "inserted": {
                "news_source_id": int(source_id),
                "article_id": int(article_id),
                "event_id": int(event_id),
                "collection_run_id": int(collection_run_id),
            },
            "counts": {
                "daily_events": int(counts["daily_events"]),
                "breaking_events": int(counts["breaking_events"]),
            },
        }
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()
