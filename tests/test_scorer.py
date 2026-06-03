from datetime import datetime, timedelta, timezone
from news_system.schemas import Article
from news_system.processors.event_clusterer import Event
from news_system.processors.scorer import score_event


def test_score_event_sets_three_scores_and_final():
    e=Event(title='war update', articles=[Article(title='war',url='https://a',published_at=datetime.now(timezone.utc),source_name='a'), Article(title='war',url='https://b',published_at=datetime.now(timezone.utc),source_name='b')], keywords={'war'})
    score_event(e)
    # New scoring formula: velocity_score = breaking_score (>0 due to severity keyword 'war'),
    # source_diversity_score = popular_score (>0 with 2 sources),
    # severity_score = importance_score (includes category_importance and severity_keyword),
    # final_score = weighted blend of popular and importance scores
    assert e.velocity_score > 0
    assert e.source_diversity_score > 0
    assert e.severity_score > 0
    assert e.final_score > 0
    assert e.breaking_score > 0
    assert isinstance(e.score_breakdown, dict)
    assert e.last_scored_at is not None


def test_category_importance_weights_updated():
    from news_system.processors.scorer import CATEGORY_IMPORTANCE
    assert CATEGORY_IMPORTANCE["war_conflict"] == 1.00
    assert CATEGORY_IMPORTANCE["politics"] == 0.80
    assert CATEGORY_IMPORTANCE["health"] == 0.85
    assert CATEGORY_IMPORTANCE["disaster"] == 0.95
    assert CATEGORY_IMPORTANCE["cybersecurity"] == 0.75


def test_source_credibility_score_uses_average_and_trusted_count():
    now = datetime.now(timezone.utc)
    articles = [
        Article(
            title="a", url="https://a.com", published_at=now,
            source_name="Source A", source_domain="a.com",
            raw={"source_config": {"credibility_score": 0.95}},
        ),
        Article(
            title="b", url="https://b.com", published_at=now,
            source_name="Source B", source_domain="b.com",
            raw={"source_config": {"credibility_score": 0.50}},
        ),
        Article(
            title="c", url="https://c.com", published_at=now,
            source_name="Source C", source_domain="c.com",
            raw={"source_config": {"credibility_score": 0.80}},
        ),
    ]
    event = Event(title="test", articles=articles, keywords={"test"})
    score_event(event)
    breakdown = event.score_breakdown["importance_score"]["source_credibility_score"]
    assert "average_credibility_score" in breakdown
    assert "trusted_source_count_score" in breakdown
    assert "final" in breakdown
    # avg = (0.95 + 0.50 + 0.80) / 3 = 0.75
    assert breakdown["average_credibility_score"] == 0.75
    # trusted count = 2 (0.95, 0.80 >= 0.75) → score = min(2/4, 1.0) = 0.5
    assert breakdown["trusted_source_count_score"] == 0.5
    # final = 0.6 * 0.75 + 0.4 * 0.5 = 0.45 + 0.20 = 0.65
    assert breakdown["final"] == 0.65


def test_recent_velocity_uses_3h_window():
    now = datetime.now(timezone.utc)
    articles = [
        Article(title="a", url="https://a.com", published_at=now, source_name="A"),
        Article(title="b", url="https://b.com", published_at=now - timedelta(hours=2), source_name="B"),
        Article(title="c", url="https://c.com", published_at=now - timedelta(hours=4), source_name="C"),
    ]
    event = Event(title="test", articles=articles, keywords={"test"})
    score_event(event)
    # Articles within last 3 hours: a (now), b (2h ago) → count=2
    # recent_velocity_score = min(2 / 10, 1.0) = 0.2
    assert event.score_breakdown["popular_score"]["recent_velocity_score"] == 0.2


def test_recent_growth_uses_60m_window():
    now = datetime.now(timezone.utc)
    articles = [
        Article(title="a", url="https://a.com", published_at=now, source_name="A"),
        Article(title="b", url="https://b.com", published_at=now - timedelta(minutes=30), source_name="B"),
        Article(title="c", url="https://c.com", published_at=now - timedelta(minutes=90), source_name="C"),
    ]
    event = Event(title="test", articles=articles, keywords={"test"})
    score_event(event)
    # Articles within last 60 minutes: a (now), b (30m ago) → count=2
    # recent_growth_score = min(2 / 8, 1.0) = 0.25
    assert event.score_breakdown["breaking_score"]["recent_growth_score"] == 0.25


def test_recent_source_uses_unique_sources_in_60m():
    now = datetime.now(timezone.utc)
    articles = [
        Article(title="a", url="https://a.com", published_at=now,
                source_name="A", source_domain="a.com"),
        Article(title="b", url="https://b.com", published_at=now - timedelta(minutes=30),
                source_name="B", source_domain="b.com"),
        Article(title="c", url="https://c.com", published_at=now - timedelta(minutes=90),
                source_name="C", source_domain="c.com"),
    ]
    event = Event(title="test", articles=articles, keywords={"test"})
    score_event(event)
    # Unique sources within last 60m: a.com, b.com → count=2
    # recent_source_score = min(2 / 4, 1.0) = 0.5
    assert event.score_breakdown["breaking_score"]["recent_source_score"] == 0.5