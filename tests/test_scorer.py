from datetime import datetime, timezone
from news_system.schemas import Article
from news_system.processors.event_clusterer import Event
from news_system.processors.scorer import score_event

def test_score_event_sets_three_scores_and_final():
    e=Event(title='war update', articles=[Article(title='war',url='https://a',published_at=datetime.now(timezone.utc),source_name='a'), Article(title='war',url='https://b',published_at=datetime.now(timezone.utc),source_name='b')], keywords={'war'})
    score_event(e)
    assert e.velocity_score > 0 and e.source_diversity_score > 0 and e.severity_score == 1.0 and e.final_score > 0
