from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from news_system.collectors import GDELTCollector, NewsAPICollector
from news_system.config.sources import SourceConfig
from news_system.db.models import ArticleModel, Base, CollectionRun
from news_system.jobs import _collector_for_source, collect_job


def make_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)()


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class RecordingClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


def test_newsapi_collector_supports_endpoint_params_and_safe_mapping():
    client = RecordingClient({
        "status": "ok",
        "articles": [
            {
                "source": {"id": "bbc-news", "name": "BBC News"},
                "author": "Jane",
                "title": "Headline",
                "description": "Desc",
                "url": "https://example.com/news",
                "urlToImage": "https://example.com/img.jpg",
                "publishedAt": "2026-06-03T10:11:12Z",
                "content": "Body",
            },
            {"title": None, "url": None, "publishedAt": None},
        ],
    })
    collector = NewsAPICollector(api_key="secret", endpoint="everything", client=client)

    articles = collector.fetch(q="climate", pageSize=2)

    assert client.calls[0][0] == "https://newsapi.org/v2/everything"
    assert client.calls[0][1]["params"]["apiKey"] == "secret"
    assert client.calls[0][1]["params"]["q"] == "climate"
    assert articles[0].source_type == "newsapi"
    assert articles[0].source_id == "bbc-news"
    assert articles[0].source_name == "BBC News"
    assert articles[0].title == "Headline"
    assert articles[0].published_at == datetime(2026, 6, 3, 10, 11, 12, tzinfo=timezone.utc)
    assert articles[0].raw["source"]["name"] == "BBC News"
    assert articles[1].title == ""
    assert articles[1].url == ""


def test_newsapi_collector_requires_api_key_before_network():
    collector = NewsAPICollector(api_key="", client=RecordingClient({"articles": []}))
    with pytest.raises(ValueError, match="NewsAPI API key"):
        collector.fetch(q="anything")


def test_gdelt_collector_maps_doc_articles_and_params():
    client = RecordingClient({
        "articles": [{
            "title": "GDELT title",
            "url": "https://gdelt.example/story",
            "seendate": "20260603123000",
            "domain": "gdelt.example",
            "language": "English",
            "sourcecountry": "United States",
            "socialimage": "https://gdelt.example/img.jpg",
        }]
    })
    collector = GDELTCollector(client=client)

    articles = collector.fetch(query="earthquake", timespan="1d", maxrecords=5, sort="HybridRel")

    assert client.calls[0][0] == "https://api.gdeltproject.org/api/v2/doc/doc"
    assert client.calls[0][1]["params"] == {
        "format": "json",
        "mode": "ArtList",
        "query": "earthquake",
        "timespan": "1d",
        "maxrecords": 5,
        "sort": "HybridRel",
    }
    assert articles[0].source_type == "gdelt"
    assert articles[0].source_name == "gdelt.example"
    assert articles[0].source_domain == "gdelt.example"
    assert articles[0].language == "English"
    assert articles[0].country == "United States"
    assert articles[0].published_at == datetime(2026, 6, 3, 12, 30, tzinfo=timezone.utc)
    assert articles[0].raw["domain"] == "gdelt.example"


def test_enabled_newsapi_env_key_missing_records_collect_error(monkeypatch):
    monkeypatch.delenv("NEWSAPI_API_KEY", raising=False)
    src = SourceConfig(name="NewsAPI Test", source_type="newsapi", enabled=True, query="test", params={"api_key_env": "NEWSAPI_API_KEY"})
    db = make_session()

    result = collect_job(db=db, collectors=[_collector_for_source(src)], lookback_hours=24)

    assert result["errors"][0]["source"] == "NewsAPI Test"
    assert "NewsAPI API key" in result["errors"][0]["error"]
    run = db.execute(select(CollectionRun)).scalar_one()
    assert run.status == "failed"
    assert "NewsAPI API key" in run.error_message


def test_configured_newsapi_and_gdelt_collect_records_metadata(monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    news_src = SourceConfig(name="NewsAPI Test", source_type="newsapi", enabled=True, query="test", params={"api_key": "k"})
    gdelt_src = SourceConfig(name="GDELT Test", source_type="gdelt", enabled=True, query="test")

    monkeypatch.setattr(NewsAPICollector, "fetch", lambda self, **kw: [__import__("news_system.schemas", fromlist=["Article"]).Article(title="News", url="https://example.com/news", published_at=now, raw={})])
    monkeypatch.setattr(GDELTCollector, "fetch", lambda self, **kw: [__import__("news_system.schemas", fromlist=["Article"]).Article(title="GDELT", url="https://example.com/gdelt", published_at=now, raw={})])

    db = make_session()
    result = collect_job(db=db, collectors=[_collector_for_source(news_src), _collector_for_source(gdelt_src)], lookback_hours=24)

    assert result["inserted"] == 2
    rows = {r.source_name: r for r in db.execute(select(ArticleModel)).scalars()}
    assert rows["NewsAPI Test"].source_type == "newsapi"
    assert rows["NewsAPI Test"].raw_payload["source_config"]["source_type"] == "newsapi"
    assert rows["GDELT Test"].source_type == "gdelt"
