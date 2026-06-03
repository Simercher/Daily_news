from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from news_system.api.main import app, get_db
from news_system.db.models import ArticleModel, Base, CollectionRun, EventArticle, EventModel
from news_system.jobs import breaking_watch_job, collect_job, daily_event_job
from news_system.schemas import Article
from news_system.storage.repositories import ArticleRepository, EventRepository, SourceRepository


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)(), engine


def sample_article(title="Earthquake hits city", url="https://example.com/a", source="Reuters"):
    return Article(title=title, url=url, published_at=datetime.now(timezone.utc), source_name=source, keywords=["earthquake"], entities=["city"])


def test_create_all_creates_required_tables():
    _session, engine = make_session()
    tables = set(inspect(engine).get_table_names())
    assert {"news_sources", "articles", "events", "event_articles", "collection_runs"} <= tables


def test_sqlalchemy_metadata_matches_target_schema_columns():
    expected = {
        "news_sources": {"id", "source_type", "name", "domain", "url", "country", "language", "category", "trusted", "enabled", "priority", "created_at", "updated_at"},
        "articles": {"id", "external_id", "source_type", "source_name", "source_domain", "title", "normalized_title", "description", "content_snippet", "url", "canonical_url", "url_hash", "language", "country", "category", "published_at", "collected_at", "raw_payload", "title_hash", "content_hash", "is_duplicate", "duplicate_of_article_id", "created_at", "updated_at"},
        "events": {"id", "title", "normalized_title", "category", "severity", "event_date", "first_seen_at", "last_seen_at", "article_count", "source_count", "trusted_source_count", "country_count", "popular_score", "importance_score", "breaking_score", "final_score", "status", "is_breaking", "breaking_detected_at", "keywords", "entities", "created_at", "updated_at"},
        "event_articles": {"event_id", "article_id", "relevance_score", "is_representative", "created_at"},
        "collection_runs": {"id", "source_type", "source_name", "started_at", "finished_at", "status", "lookback_hours", "fetched_count", "inserted_count", "duplicate_count", "error_count", "error_message", "metadata", "created_at", "updated_at"},
    }
    for table_name, columns in expected.items():
        assert set(Base.metadata.tables[table_name].columns.keys()) == columns


def test_migration_file_contains_required_table_ops():
    migration = Path("alembic/versions/0001_create_news_tables.py").read_text()
    for table in ["news_sources", "articles", "events", "event_articles", "collection_runs"]:
        assert f'op.create_table("{table}"' in migration


def test_repositories_insert_list_link():
    db, _ = make_session()
    SourceRepository(db).upsert(name="Reuters", type="rss", url="https://example.com/feed")
    article, inserted = ArticleRepository(db).upsert(ArticleModel(title="Title", url="https://example.com/x?utm_source=t", published_at=datetime.now(timezone.utc), source_name="Reuters"))
    assert inserted
    event = EventRepository(db).add(EventModel(title="Title", event_date=datetime.now(timezone.utc), keywords=[], entities=[], article_count=1), [article])
    assert ArticleRepository(db).list()[0].id == article.id
    assert db.get(EventArticle, {"event_id": event.id, "article_id": article.id}) is not None


def test_jobs_collect_build_events_and_watch_breaking_with_fake_collectors():
    db, _ = make_session()

    class FakeCollector:
        source_name = "fake"
        def fetch(self, **kwargs):
            return [sample_article(title="Earthquake hits city", url="https://e.test/1", source="A"), sample_article(title="Major quake damages city", url="https://e.test/2", source="B")]

    result = collect_job(db=db, collectors=[FakeCollector()])
    assert result["inserted"] == 2
    assert db.query(CollectionRun).count() == 1

    events = daily_event_job(db=db)
    assert len(events) >= 1
    assert db.query(EventModel).count() >= 1

    breaking = breaking_watch_job(db=db, since_minutes=60)
    assert len(breaking) >= 1
    assert any(e.is_breaking for e in breaking)


def test_fastapi_endpoints_with_sqlite_session_override():
    db, _ = make_session()
    article, _ = ArticleRepository(db).upsert(ArticleModel(title="Breaking", url="https://example.com/b", published_at=datetime.now(timezone.utc), source_name="A"))
    event = EventRepository(db).add(EventModel(title="Breaking", event_date=datetime.now(timezone.utc), keywords=[], entities=[], article_count=1, final_score=0.9, is_breaking=True), [article])
    db.commit()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        assert client.get(f"/events/daily?date={today}").status_code == 200
        assert client.get("/events/breaking").status_code == 200
        detail = client.get(f"/events/{event.id}")
        assert detail.status_code == 200
        assert detail.json()["event"]["id"] == event.id
    finally:
        app.dependency_overrides.clear()
