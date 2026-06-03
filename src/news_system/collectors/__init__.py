from abc import ABC, abstractmethod
from datetime import datetime, timezone
import os

import feedparser, httpx
from news_system.schemas import Article
from news_system.processors.normalizer import to_utc

class BaseCollector(ABC):
    @abstractmethod
    def fetch(self, **kwargs) -> list[Article]: ...

class RSSCollector(BaseCollector):
    def __init__(self, feed_url: str, source_name: str|None=None): self.feed_url=feed_url; self.source_name=source_name
    def fetch(self, **kwargs):
        parsed=feedparser.parse(self.feed_url); out=[]
        for e in parsed.entries:
            dt=getattr(e,'published',None) or getattr(e,'updated',None) or datetime.now(timezone.utc).isoformat()
            out.append(Article(title=e.get('title',''), url=e.get('link',''), published_at=to_utc(dt), source_name=self.source_name or parsed.feed.get('title'), description=e.get('summary'), raw=dict(e)))
        return out

class NewsAPICollector(BaseCollector):
    VALID_ENDPOINTS = {"top-headlines", "everything"}

    def __init__(self, api_key: str | None = None, endpoint='top-headlines', base_url='https://newsapi.org/v2', *, api_key_env: str | None = None, client=None):
        self.api_key = api_key or (os.getenv(api_key_env) if api_key_env else None)
        self.api_key_env = api_key_env
        self.endpoint = endpoint or 'top-headlines'
        if self.endpoint not in self.VALID_ENDPOINTS:
            raise ValueError(f"unsupported NewsAPI endpoint: {self.endpoint}")
        self.base_url = base_url.rstrip('/')
        self.client = client or httpx

    def fetch(self, **params):
        if not self.api_key:
            raise ValueError("NewsAPI API key is required (set api_key or api_key_env/NEWSAPI_API_KEY)")
        params = {k: v for k, v in params.items() if k not in {"api_key", "api_key_env", "endpoint"} and v is not None}
        params["apiKey"] = self.api_key
        r = self.client.get(f"{self.base_url}/{self.endpoint}", params=params, timeout=20)
        r.raise_for_status()
        out = []
        for a in (r.json() or {}).get('articles', []) or []:
            source = a.get('source') or {}
            published = a.get('publishedAt') or datetime.now(timezone.utc)
            out.append(Article(
                source_type='newsapi',
                title=a.get('title') or '',
                url=a.get('url') or '',
                published_at=to_utc(published),
                source_id=source.get('id'),
                source_name=source.get('name'),
                author=a.get('author'),
                description=a.get('description'),
                content=a.get('content'),
                image_url=a.get('urlToImage'),
                raw=dict(a),
            ))
        return out

class GDELTCollector(BaseCollector):
    def __init__(self, base_url='https://api.gdeltproject.org/api/v2/doc/doc', *, client=None):
        self.base_url = base_url
        self.client = client or httpx

    @staticmethod
    def _parse_seen_date(value):
        if not value:
            return datetime.now(timezone.utc)
        text = str(value)
        if text.isdigit() and len(text) == 14:
            return datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        if text.isdigit() and len(text) == 8:
            return datetime.strptime(text, "%Y%m%d").replace(tzinfo=timezone.utc)
        return to_utc(text)

    def fetch(self, **params):
        q = {'format': 'json', 'mode': 'ArtList'}
        for key in ('query', 'timespan', 'maxrecords', 'sort', 'startdatetime', 'enddatetime', 'sourcelang', 'sourcecountry', 'domain'):
            if params.get(key) is not None:
                q[key] = params[key]
        r = self.client.get(self.base_url, params=q, timeout=20)
        r.raise_for_status()
        out = []
        for a in (r.json() or {}).get('articles', []) or []:
            domain = a.get('domain')
            out.append(Article(
                source_type='gdelt',
                title=a.get('title') or '',
                url=a.get('url') or '',
                published_at=self._parse_seen_date(a.get('seendate')),
                source_name=domain,
                source_domain=domain,
                language=a.get('language'),
                country=a.get('sourcecountry'),
                image_url=a.get('socialimage'),
                raw=dict(a),
            ))
        return out
