from datetime import datetime, timezone, timedelta
from news_system.schemas import Article
from news_system.processors.deduplicator import mark_duplicates

def A(title,url,dt=None): return Article(title=title,url=url,published_at=dt or datetime.now(timezone.utc))

def test_url_hash_duplicate():
    arts=mark_duplicates([A('x','https://a.com/p?utm_source=1'), A('y','https://a.com/p')])
    assert arts[1].is_duplicate

def test_fuzzy_title_duplicate_within_48h():
    now=datetime.now(timezone.utc)
    arts=mark_duplicates([A('Earthquake hits city','https://a.com/1',now), A('Earthquake hits the city','https://a.com/2',now+timedelta(hours=1))])
    assert arts[1].is_duplicate
