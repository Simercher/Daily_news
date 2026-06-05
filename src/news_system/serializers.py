from __future__ import annotations

from datetime import date, datetime

from news_system.db.models import ArticleModel, EventModel
from news_system.processors.scorer import _get_credibility
from news_system.search.types import SearchQuery, SearchResult


def _iso(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def article_to_dict(article: ArticleModel) -> dict:
    """Serialize an ArticleModel to the API response dict format."""
    return {
        "id": article.id,
        "title": article.title,
        "normalized_title": article.normalized_title,
        "url": article.url,
        "canonical_url": article.canonical_url,
        "source_name": article.source_name,
        "source_domain": article.source_domain,
        "source_type": article.source_type,
        "published_at": _iso(article.published_at),
        "collected_at": _iso(article.collected_at),
        "credibility_score": _get_credibility(article),
        "fulltext_quality_score": article.fulltext_quality_score,
        "fulltext_status": article.fulltext_status,
        "language": article.language,
        "country": article.country,
        "category": article.category,
        "description": article.description,
        "is_duplicate": article.is_duplicate,
    }


def search_query_plan_to_dict(query: SearchQuery) -> dict:
    return {
        "must_terms": query.must_terms,
        "should_terms": query.should_terms,
        "must_not_terms": query.must_not_terms,
        "must_phrases": query.must_phrases,
        "should_phrases": query.should_phrases,
        "must_not_phrases": query.must_not_phrases,
        "has_explicit_or": query.has_explicit_or,
    }


def search_result_to_dict(result: SearchResult) -> dict:
    item = article_to_dict(result.article)
    item["content_snippet"] = result.article.content_snippet
    item["score"] = result.score
    item["matched_fields"] = result.matched_fields
    item["matched_terms"] = result.matched_terms
    return item


def select_representative_articles(articles: list[ArticleModel]) -> list[ArticleModel]:
    """Select up to 5 representative articles, max 1 per source_domain.

    Criteria:
    - credibility_score >= 0.75 (from raw_payload.source_config.credibility_score)
    - fulltext_quality_score >= 0.4
    - is_duplicate = false
    - Max 1 article per source_domain
    - Max 5 articles total
    """
    candidates = [
        a
        for a in articles
        if not a.is_duplicate
        and a.fulltext_quality_score >= 0.4
        and _get_credibility(a) >= 0.75
    ]
    # Sort by credibility_score desc, then fulltext_quality_score desc
    candidates.sort(
        key=lambda a: (_get_credibility(a), a.fulltext_quality_score),
        reverse=True,
    )
    seen_domains: set[str | None] = set()
    result: list[ArticleModel] = []
    for a in candidates:
        domain = a.source_domain
        if domain is not None and domain in seen_domains:
            continue
        if domain is not None:
            seen_domains.add(domain)
        result.append(a)
        if len(result) >= 5:
            break
    return result


def get_trusted_articles(articles: list[ArticleModel]) -> list[ArticleModel]:
    """Filter articles where credibility_score >= 0.75 and fulltext_quality_score >= 0.4."""
    return [
        a
        for a in articles
        if _get_credibility(a) >= 0.75 and a.fulltext_quality_score >= 0.4
    ]


def event_to_dict(event: EventModel) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "normalized_title": event.normalized_title,
        "event_date": _iso(event.event_date),
        "first_seen_at": _iso(event.first_seen_at),
        "last_seen_at": _iso(event.last_seen_at),
        "article_count": event.article_count,
        "source_count": event.source_count,
        "trusted_source_count": event.trusted_source_count,
        "category": event.category,
        "popular_score": event.popular_score,
        "importance_score": event.importance_score,
        "breaking_score": event.breaking_score,
        "final_score": event.final_score,
        "is_breaking": event.is_breaking,
        "breaking_detected_at": _iso(event.breaking_detected_at),
        "keywords": event.keywords or [],
        "entities": event.entities or {},
        "score_breakdown": event.score_breakdown or {},
    }


def enrich_event_with_articles(event_dict: dict, articles: list[ArticleModel]) -> dict:
    """Add representative_articles, trusted_articles, and all_articles to an event dict."""
    event_dict["representative_articles"] = [
        article_to_dict(a) for a in select_representative_articles(articles)
    ]
    event_dict["trusted_articles"] = [
        article_to_dict(a) for a in get_trusted_articles(articles)
    ]
    event_dict["all_articles"] = [article_to_dict(a) for a in articles]
    return event_dict


def events_payload(
    events: list[EventModel],
    articles_by_event: dict[int, list[ArticleModel]] | None = None,
    **extra,
) -> dict:
    enriched = []
    for e in events:
        ed = event_to_dict(e)
        if articles_by_event and e.id in articles_by_event:
            enrich_event_with_articles(ed, articles_by_event[e.id])
        enriched.append(ed)
    return {**extra, "count": len(events), "events": enriched}
