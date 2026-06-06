from __future__ import annotations

from datetime import datetime, timezone
import os
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Load .env before importing project DB/session code.
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from news_system.cli import _prepare_schema_for_cli
from news_system.db.models import ArticleModel, Base
from news_system.jobs import collect_job
from news_system.storage.repositories import ArticleRepository


DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL.startswith(("postgresql://", "postgresql+psycopg://")):
    pytest.skip("DATABASE_URL not set or not PostgreSQL; skipping article search PostgreSQL integration tests", allow_module_level=True)


@pytest.fixture()
def pg_session():
    schema = f"article_search_it_{uuid.uuid4().hex[:8]}"
    admin_engine = create_engine(DATABASE_URL, future=True)
    with admin_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    admin_engine.dispose()

    search_path = quote(f"-csearch_path={schema}")
    schema_url = f"{DATABASE_URL}?options={search_path}"
    alembic_url = schema_url.replace("%", "%%")
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", alembic_url)
    command.upgrade(cfg, "head")

    engine = create_engine(schema_url, future=True)
    session = Session(engine, future=True)
    try:
        yield session, engine, schema
    finally:
        session.close()
        engine.dispose()
        cleanup_engine = create_engine(DATABASE_URL, future=True)
        with cleanup_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        cleanup_engine.dispose()


def _add_article(session: Session, title: str, url: str, *, description: str | None = None, content: str | None = None, source: str = "Reuters", category: str = "world", is_duplicate: bool = False):
    article = ArticleModel(
        title=title,
        description=description,
        content_snippet=content,
        url=url,
        source_name=source,
        source_domain="reuters.example",
        source_type="rss",
        category=category,
        raw_payload={"source_config": {"name": source, "trusted": True}},
        is_duplicate=is_duplicate,
        published_at=datetime.now(timezone.utc),
    )
    ArticleRepository(session).add(article)
    session.flush()
    return article


def test_search_vector_migration_and_gin_index_exist(pg_session):
    session, _engine, schema = pg_session
    row = session.execute(text("SELECT data_type FROM information_schema.columns WHERE table_schema = :schema AND table_name = 'articles' AND column_name = 'search_vector'"), {"schema": schema}).one()
    assert row[0] == "tsvector"
    index_rows = session.execute(text("SELECT indexdef FROM pg_indexes WHERE schemaname = :schema AND tablename = 'articles' AND indexname = 'ix_articles_search_vector'"), {"schema": schema}).all()
    assert len(index_rows) == 1
    assert "USING gin" in index_rows[0][0]


def test_postgres_search_parsed_enforces_phrase_negation_and_integer_score(pg_session):
    session, _engine, _schema = pg_session
    repo = ArticleRepository(session)
    _add_article(
        session,
        "NASA tracks Mars rover convoy",
        "https://example.com/mars-rover",
        description="Mars rover mission update from NASA",
        content="The mars rover continues its mission.",
    )
    _add_article(
        session,
        "NASA sports desk mentions rover",
        "https://example.com/sports",
        description="sports bulletin",
        content="mars rover",
    )
    session.commit()

    results = repo.search('"mars rover" nasa -sports', limit=10, lookback_hours=24)
    assert [result.article.url for result in results] == ["https://example.com/mars-rover"]
    assert isinstance(results[0].score, int)
    assert results[0].score > 0
    assert results[0].matched_terms == ["nasa", "mars rover"]


def test_postgres_search_ranking_and_filters(pg_session):
    session, _engine, _schema = pg_session
    repo = ArticleRepository(session)
    _add_article(
        session,
        "Mars rover NASA mission",
        "https://example.com/strong",
        description="NASA rover mission update",
        content="Mars rover mission update",
    )
    _add_article(
        session,
        "Briefing",
        "https://example.com/weak",
        description="General science news",
        content="Mars rover mentioned alongside NASA in passing",
    )
    _add_article(
        session,
        "Mars rover NASA business note",
        "https://example.com/business",
        description="Business desk",
        content="Mars rover NASA business note",
        category="business",
        is_duplicate=True,
    )
    session.commit()

    results = repo.search("mars rover nasa", limit=10, lookback_hours=24, source="Reuters", category="world")
    assert [result.article.url for result in results] == ["https://example.com/strong", "https://example.com/weak"]
    assert results[0].score >= results[1].score


def test_postgres_search_preserves_sqlite_inclusion_semantics_for_substrings_special_tokens_and_boolean_queries(pg_session):
    pg_db, _engine, _schema = pg_session
    sqlite_engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(sqlite_engine)
    sqlite_db = Session(sqlite_engine, future=True)
    try:
        for db in (pg_db, sqlite_db):
            _add_article(db, "Rain delays election", "https://example.com/rain", description="Storms slow vote counting")
            _add_article(db, "AI policy briefing", "https://example.com/ai", description="Regulators debate AI systems")
            _add_article(db, "C++ standards committee meets", "https://example.com/c-plus-plus", description="Programming language update")
            _add_article(db, "C suite reshuffle", "https://example.com/c-suite", description="Executives change roles")
            _add_article(db, "NASA tracks Mars rover convoy", "https://example.com/mars-rover", description="Mars rover mission update from NASA", content="The mars rover continues its mission.")
            _add_article(db, "NASA sports desk mentions rover", "https://example.com/sports", description="sports bulletin", content="mars rover")
            _add_article(db, "Taiwan watches South China Sea supply routes", "https://example.com/supply-routes", description="TSMC suppliers monitor the corridor", content="Officials say south china sea shipping lanes matter to Taiwan")
            _add_article(db, "Taiwan sports broadcast covers South China Sea race", "https://example.com/sports-race", description="TSMC is not involved", content="south china sea race highlights")
            db.commit()

        cases = [
            "ai",
            "C++",
            '\"mars rover\" nasa -sports',
            '\"south china sea\" taiwan OR tsmc -sports',
        ]
        for raw_query in cases:
            sqlite_urls = {result.article.url for result in ArticleRepository(sqlite_db).search(raw_query, limit=20, lookback_hours=24)}
            postgres_urls = {result.article.url for result in ArticleRepository(pg_db).search(raw_query, limit=20, lookback_hours=24)}
            assert postgres_urls == sqlite_urls, raw_query
    finally:
        sqlite_db.close()
        sqlite_engine.dispose()


def test_postgres_cli_schema_preparation_rejects_fresh_unmigrated_schema(pg_session):
    _session, _engine, schema = pg_session
    fresh_schema = f"{schema}_fresh"
    admin_engine = create_engine(DATABASE_URL, future=True)
    with admin_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{fresh_schema}"'))
    admin_engine.dispose()

    search_path = quote(f"-csearch_path={fresh_schema}")
    fresh_engine = create_engine(f"{DATABASE_URL}?options={search_path}", future=True)
    try:
        with pytest.raises(RuntimeError, match="PostgreSQL schema is not initialized with Alembic migrations"):
            _prepare_schema_for_cli(fresh_engine)
        with fresh_engine.connect() as conn:
            assert not conn.execute(text("SELECT to_regclass('articles')")).scalar_one()
    finally:
        fresh_engine.dispose()
        cleanup_engine = create_engine(DATABASE_URL, future=True)
        with cleanup_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{fresh_schema}" CASCADE'))
        cleanup_engine.dispose()


def test_collect_job_db_owning_postgres_init_rejects_fresh_unmigrated_schema(pg_session, monkeypatch):
    _session, _engine, schema = pg_session
    fresh_schema = f"{schema}_collect_fresh"
    admin_engine = create_engine(DATABASE_URL, future=True)
    with admin_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{fresh_schema}"'))
    admin_engine.dispose()

    search_path = quote(f"-csearch_path={fresh_schema}")
    schema_url = f"{DATABASE_URL}?options={search_path}"
    monkeypatch.setenv("DATABASE_URL", schema_url)
    fresh_engine = create_engine(schema_url, future=True)
    try:
        with pytest.raises(RuntimeError, match="PostgreSQL schema is not initialized with Alembic migrations"):
            collect_job(collectors=[])
        with fresh_engine.connect() as conn:
            assert not conn.execute(text("SELECT to_regclass('articles')")).scalar_one()
    finally:
        fresh_engine.dispose()
        cleanup_engine = create_engine(DATABASE_URL, future=True)
        with cleanup_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{fresh_schema}" CASCADE'))
        cleanup_engine.dispose()
