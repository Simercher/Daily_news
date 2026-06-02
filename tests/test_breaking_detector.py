from datetime import datetime, timezone
from news_system.schemas import Article
from news_system.processors.event_clusterer import Event
from news_system.processors.breaking_detector import is_breaking

def test_high_severity_relaxes_breaking_conditions():
    arts=[Article(title='earthquake',url='https://a',published_at=datetime.now(timezone.utc),source_name='a'), Article(title='earthquake',url='https://b',published_at=datetime.now(timezone.utc),source_name='a')]
    e=Event(title='major earthquake', articles=arts, keywords={'earthquake'})
    assert is_breaking(e)
