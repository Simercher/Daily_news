from __future__ import annotations

from sqlalchemy.dialects import postgresql

from news_system.search.query_parser import parse_search_query
from news_system.storage.repositories import ArticleRepository


class _FakeBind:
    def __init__(self, dialect_name: str):
        self.dialect = type("Dialect", (), {"name": dialect_name})()


class _FakeSession:
    def __init__(self, dialect_name: str):
        self._bind = _FakeBind(dialect_name)

    def get_bind(self):
        return self._bind


class _EmptyResult:
    def all(self):
        return []


class _RecordingPostgresSession:
    def __init__(self):
        self._bind = postgresql.dialect()
        self.statement = None

    def get_bind(self):
        return type("Bind", (), {"dialect": self._bind})()

    def execute(self, statement):
        self.statement = statement
        return _EmptyResult()


def test_search_parsed_dispatches_by_sqlalchemy_dialect(monkeypatch):
    parsed = parse_search_query('"south china sea" taiwan OR tsmc -sports')
    calls: list[tuple[str, dict]] = []

    def fake_sqlite(self, query, **kwargs):
        calls.append(("sqlite", {"query": query, **kwargs}))
        return ["sqlite-result"]

    def fake_postgres(self, query, **kwargs):
        calls.append(("postgresql", {"query": query, **kwargs}))
        return ["postgres-result"]

    monkeypatch.setattr(ArticleRepository, "_search_sqlite_like", fake_sqlite, raising=False)
    monkeypatch.setattr(ArticleRepository, "_search_postgres_fts", fake_postgres, raising=False)

    sqlite_results = ArticleRepository(_FakeSession("sqlite")).search_parsed(
        parsed,
        limit=7,
        lookback_hours=12,
        source="Reuters",
        category="world",
        include_duplicates=True,
    )
    postgres_results = ArticleRepository(_FakeSession("postgresql")).search_parsed(
        parsed,
        limit=7,
        lookback_hours=12,
        source="Reuters",
        category="world",
        include_duplicates=True,
    )

    assert sqlite_results == ["sqlite-result"]
    assert postgres_results == ["postgres-result"]
    assert [(backend, payload["query"]) for backend, payload in calls] == [("sqlite", parsed), ("postgresql", parsed)]
    assert all(payload["limit"] == 7 for _, payload in calls)
    assert all(payload["lookback_hours"] == 12 for _, payload in calls)
    assert all(payload["source"] == "Reuters" for _, payload in calls)
    assert all(payload["category"] == "world" for _, payload in calls)
    assert all(payload["include_duplicates"] is True for _, payload in calls)


def test_postgres_backend_emits_phase_one_filters_and_fts_rank_statement():
    parsed = parse_search_query('"south china sea" taiwan OR tsmc -sports')
    session = _RecordingPostgresSession()

    results = ArticleRepository(session)._search_postgres_fts(
        parsed,
        limit=5,
        lookback_hours=None,
        source=None,
        category=None,
        include_duplicates=False,
    )

    assert results == []
    statement = session.statement
    assert statement is not None
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "ts_rank_cd" in sql
    assert "search_vector @@ to_tsquery" not in sql
    assert "lower(coalesce(articles.title" in sql
    assert "LIKE" in sql
    assert "ORDER BY search_score DESC" in sql
