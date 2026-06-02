from abc import ABC, abstractmethod
from datetime import datetime, timezone
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
    def __init__(self, api_key: str, endpoint='top-headlines', base_url='https://newsapi.org/v2'):
        self.api_key=api_key; self.endpoint=endpoint; self.base_url=base_url
    def fetch(self, **params):
        r=httpx.get(f"{self.base_url}/{self.endpoint}", params={**params,'apiKey':self.api_key}, timeout=20); r.raise_for_status()
        return [Article(title=a.get('title') or '', url=a.get('url') or '', published_at=to_utc(a.get('publishedAt')), source_id=(a.get('source') or {}).get('id'), source_name=(a.get('source') or {}).get('name'), author=a.get('author'), description=a.get('description'), content=a.get('content'), image_url=a.get('urlToImage'), raw=a) for a in r.json().get('articles',[])]

class GDELTCollector(BaseCollector):
    def __init__(self, base_url='https://api.gdeltproject.org/api/v2/doc/doc'): self.base_url=base_url
    def fetch(self, **params):
        q={'format':'json','mode':'ArtList',**params}
        r=httpx.get(self.base_url, params=q, timeout=20); r.raise_for_status()
        return [Article(title=a.get('title') or '', url=a.get('url') or '', published_at=to_utc(a.get('seendate') or datetime.now(timezone.utc)), source_name=a.get('domain'), language=a.get('language'), country=a.get('sourcecountry'), image_url=a.get('socialimage'), raw=a) for a in r.json().get('articles',[])]
