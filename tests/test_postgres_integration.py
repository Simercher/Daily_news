"""PostgreSQL integration smoke test. Loads .env before import."""
import os
from pathlib import Path

import pytest

# Load .env BEFORE importing anything from news_system.db.session
# (so engine/SessionLocal are initialized with the correct host)
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

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
        "breaking_alert_states",
    }
    assert result["inserted"]["news_source_id"] > 0
    assert result["inserted"]["article_id"] > 0
    assert result["inserted"]["event_id"] > 0
    assert result["inserted"]["collection_run_id"] > 0
    assert result["counts"]["daily_events"] >= 1
    assert result["counts"]["breaking_events"] >= 1