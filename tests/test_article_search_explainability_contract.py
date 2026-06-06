from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from news_system.db.models import ArticleModel, Base
from news_system.search.query_parser import parse_search_query
from news_system.serializers import search_query_plan_to_dict
from news_system.storage.repositories import ArticleRepository


class _RecordingPostgresSession:
    def __init__(self):
        self._bind = postgresql.dialect()
        self.statement = None

    def get_bind(self):
        return type("Bind", (), {"dialect": self._bind})()

    def execute(self, statement):
        self.statement = statement

        class _EmptyResult:
            def all(self):
                return []

        return _EmptyResult()


def _make_sqlite_session():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)(), engine


def _add_article(db, title: str, url: str, *, description: str | None = None, content: str | None = None):
    article = ArticleModel(
        title=title,
        description=description,
        content_snippet=content,
        url=url,
        source_name="Reuters",
        source_domain="reuters.example",
        source_type="rss",
        category="world",
        published_at=datetime.now(timezone.utc) - timedelta(hours=1),
        raw_payload={"source_config": {"name": "Reuters", "trusted": True}},
    )
    ArticleRepository(db).add(article)
    db.commit()
    return article


def test_postgres_backend_uses_phase_one_filters_fts_rank_and_preserves_query_plan_shape():
    parsed = parse_search_query('"mars rover" nasa -sports')
    session = _RecordingPostgresSession()

    results = ArticleRepository(session).search_parsed(parsed, limit=5, lookback_hours=24)

    assert results == []
    statement = session.statement
    assert statement is not None
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ts_rank_cd" in sql
    assert "search_vector @@ to_tsquery" not in sql
    assert "lower(coalesce(articles.title" in sql
    assert "LIKE" in sql
    assert search_query_plan_to_dict(parsed) == {
        "must_terms": ["nasa"],
        "should_terms": [],
        "must_not_terms": ["sports"],
        "must_phrases": ["mars rover"],
        "should_phrases": [],
        "must_not_phrases": [],
        "has_explicit_or": False,
    }


def test_sqlite_results_preserve_score_and_match_metadata_for_final_rows():
    db, engine = _make_sqlite_session()
    try:
        article = _add_article(
            db,
            "NASA tracks Mars rover convoy",
            "https://example.com/mars-rover",
            description="Mars rover mission update from NASA",
            content="The mars rover continues its mission.",
        )
        results = ArticleRepository(db).search('"mars rover" nasa -sports', limit=5, lookback_hours=24)
        assert [result.article.id for result in results] == [article.id]
        result = results[0]
        assert isinstance(result.score, int)
        assert result.score > 0
        assert result.matched_fields == ["title", "description", "content_snippet"]
        assert result.matched_terms == ["nasa", "mars rover"]
    finally:
        db.close()
        engine.dispose()
