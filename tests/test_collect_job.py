from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from news_system.cli import main
from news_system.db.models import ArticleModel, Base, CollectionRun, NewsSource
from news_system.jobs import collect_job
from news_system.schemas import Article
from news_system.config.sources import SourceConfig


class FakeCollector:
    def __init__(self, articles, *, name="Fake RSS", fail=False):
        self.articles = articles
        self.source_name = name
        self.source_type = "rss"
        self.source_config = SourceConfig(
            name=name,
            source_type="rss",
            enabled=True,
            url="https://example.com/feed.xml",
            trusted=True,
            priority=7,
            language="en",
            category="world",
        )
        self.fail = fail

    def fetch(self, **kwargs):
        if self.fail:
            raise RuntimeError("boom")
        return list(self.articles)


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


def article(title, url, hours_old=1):
    return Article(
        title=title,
        url=url,
        published_at=datetime.now(timezone.utc) - timedelta(hours=hours_old),
        description="desc",
    )


def test_collect_job_writes_articles_metadata_and_stats():
    db = make_session()
    result = collect_job(
        db=db,
        source="rss",
        lookback_hours=24,
        collectors=[FakeCollector([
            article("Hello World", "https://www.example.com/a?utm_source=x&b=1"),
            article("Old", "https://example.com/old", hours_old=72),
        ])],
    )

    assert result["fetched"] == 2
    assert result["filtered_old"] == 1
    assert result["inserted"] == 1
    assert result["duplicates"] == 0
    assert result["source_counts"] == {"Fake RSS": {"fetched": 2, "inserted": 1, "duplicates": 0, "filtered_old": 1, "errors": 0}}

    src = db.execute(select(NewsSource).where(NewsSource.name == "Fake RSS")).scalar_one()
    assert src.trusted is True
    assert src.priority == 7

    row = db.execute(select(ArticleModel)).scalar_one()
    assert row.canonical_url == "https://example.com/a?b=1"
    assert row.url_hash
    assert row.title_hash
    assert row.content_hash
    assert row.source_name == "Fake RSS"


def test_collect_job_rerun_same_url_upserts_as_duplicate_stat():
    db = make_session()
    collector = FakeCollector([article("Same", "https://example.com/same?utm_campaign=x")])
    first = collect_job(db=db, source="rss", lookback_hours=24, collectors=[collector])
    second = collect_job(db=db, source="rss", lookback_hours=24, collectors=[collector])

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["duplicates"] == 1
    assert len(db.execute(select(ArticleModel)).scalars().all()) == 1


def test_collect_job_records_failed_source_run():
    db = make_session()
    result = collect_job(db=db, collectors=[FakeCollector([], fail=True)], lookback_hours=24)
    assert result["errors"] == [{"source": "Fake RSS", "error": "boom"}]
    run = db.execute(select(CollectionRun)).scalar_one()
    assert run.status == "failed"
    assert run.error_count == 1
    assert run.error_message == "boom"


def test_collect_job_positional_arguments_preserve_compatibility():
    db = make_session()
    result = collect_job(
        db,
        "rss",
        24,
        [FakeCollector([article("Positional", "https://example.com/positional")])],
    )

    assert result["fetched"] == 1
    assert result["inserted"] == 1
    assert result["duplicates"] == 0


def test_cli_collect_smoke_with_fake_db_and_collector(monkeypatch, tmp_path, capsys):
    db_url = f"sqlite+pysqlite:///{tmp_path / 'news.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    def fake_load_collectors(source, config_path):
        return [FakeCollector([article("CLI", "https://example.com/cli")])]

    monkeypatch.setattr("news_system.jobs._load_collectors", fake_load_collectors)
    main(["collect", "--source", "rss", "--lookback-hours", "24"])
    out = json.loads(capsys.readouterr().out)
    assert out["fetched"] == 1
    assert out["inserted"] == 1
    assert out["duplicates"] == 0
    assert out["source_counts"]["Fake RSS"]["inserted"] == 1
