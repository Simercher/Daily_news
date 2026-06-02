from datetime import datetime, timezone
from news_system.schemas import Article
from news_system.processors.deduplicator import mark_duplicates
from news_system.processors.event_clusterer import cluster_events

def test_cluster_by_title_similarity():
    now=datetime.now(timezone.utc)
    arts=mark_duplicates([Article(title='Major quake hits Taipei',url='https://a/1',published_at=now,source_name='a'), Article(title='Major earthquake hits Taipei',url='https://b/2',published_at=now,source_name='b')])
    ev=cluster_events(arts, now=now)
    assert len(ev)==1 and len(ev[0].articles)==2

def test_cluster_by_keyword_overlap_same_entity():
    now=datetime.now(timezone.utc)
    arts=[Article(title='A',url='https://a/1',published_at=now,keywords=['ai','chip'],entities=['Nvidia']), Article(title='B',url='https://b/2',published_at=now,keywords=['ai','chip'],entities=['Nvidia'])]
    ev=cluster_events(arts, now=now)
    assert len(ev)==1
