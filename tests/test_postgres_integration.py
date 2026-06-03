import os

import pytest

from news_system.storage.smoke import run_db_smoke


@pytest.mark.integration
def test_postgres_db_smoke_requires_database_url():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is not set; skipping PostgreSQL integration smoke test")
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.skip("DATABASE_URL is not PostgreSQL; skipping PostgreSQL integration smoke test")

    result = run_db_smoke()

    assert result["ok"] is True
    assert set(result["tables"]) == {
        "articles",
        "news_sources",
        "events",
        "event_articles",
        "collection_runs",
    }
    assert result["inserted"]["news_source_id"] > 0
    assert result["inserted"]["article_id"] > 0
    assert result["inserted"]["event_id"] > 0
    assert result["inserted"]["collection_run_id"] > 0
    assert result["counts"]["daily_events"] >= 1
    assert result["counts"]["breaking_events"] >= 1
