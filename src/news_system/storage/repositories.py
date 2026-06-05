from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from news_system.db.models import ArticleModel, CollectionRun, EventArticle, EventModel, NewsSource
from news_system.processors.normalizer import canonicalize_url, content_hash, normalize_title, title_hash, url_hash
from news_system.search.query_parser import parse_search_query
from news_system.search.scoring import build_filter_expressions, build_score_expression, compute_python_match_metadata
from news_system.search.types import SearchQuery, SearchResult


class SourceRepository:
    def __init__(self, db: Session): self.db = db

    def upsert(self, *, name: str, source_type: str | None = None, type: str | None = None, url: str | None = None, **fields) -> NewsSource:
        source_type = source_type or type or "rss"
        obj = self.db.execute(select(NewsSource).where(NewsSource.name == name)).scalar_one_or_none()
        if obj is None:
            obj = NewsSource(name=name, source_type=source_type, url=url, **fields)
            self.db.add(obj)
        else:
            obj.source_type = source_type or obj.source_type; obj.url = url or obj.url
            for k, v in fields.items(): setattr(obj, k, v)
        self.db.flush(); return obj

    def list_enabled(self) -> list[NewsSource]:
        return list(self.db.execute(select(NewsSource).where(NewsSource.enabled == True)).scalars())


class ArticleRepository:
    def __init__(self, db: Session): self.db = db

    def _prepare(self, article: ArticleModel) -> ArticleModel:
        article.canonical_url = article.canonical_url or canonicalize_url(article.url)
        article.url_hash = article.url_hash or url_hash(article.url)
        article.normalized_title = article.normalized_title or normalize_title(article.title)
        article.title_hash = article.title_hash or title_hash(article.title)
        article.content_hash = article.content_hash or content_hash(article.content_snippet or article.description)
        if article.published_at.tzinfo is None:
            article.published_at = article.published_at.replace(tzinfo=timezone.utc)
        return article

    def add(self, article: ArticleModel) -> ArticleModel:
        self.db.add(self._prepare(article)); self.db.flush(); return article

    def upsert(self, article: ArticleModel) -> tuple[ArticleModel, bool]:
        self._prepare(article)
        existing = self.db.execute(select(ArticleModel).where(ArticleModel.url_hash == article.url_hash)).scalar_one_or_none()
        if existing:
            return existing, False
        self.db.add(article); self.db.flush(); return article, True

    def get(self, article_id: int) -> ArticleModel | None: return self.db.get(ArticleModel, article_id)

    def list_recent(self, *, hours: int = 24, include_duplicates: bool = False, limit: int | None = None) -> list[ArticleModel]:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = select(ArticleModel).where(ArticleModel.published_at >= since)
        if not include_duplicates: stmt = stmt.where(ArticleModel.is_duplicate == False)
        stmt = stmt.order_by(ArticleModel.published_at.desc())
        if limit: stmt = stmt.limit(limit)
        rows = list(self.db.execute(stmt).scalars())
        for row in rows:
            row.ensure_utc()
        return rows

    def list(self, limit: int = 100) -> list[ArticleModel]:
        return list(self.db.execute(select(ArticleModel).order_by(ArticleModel.published_at.desc()).limit(limit)).scalars())

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        lookback_hours: int | None = None,
        source: str | None = None,
        category: str | None = None,
        include_duplicates: bool = False,
    ) -> list[SearchResult]:
        parsed = parse_search_query(query)
        return self.search_parsed(
            parsed,
            limit=limit,
            lookback_hours=lookback_hours,
            source=source,
            category=category,
            include_duplicates=include_duplicates,
        )

    def search_parsed(
        self,
        query: SearchQuery,
        *,
        limit: int = 20,
        lookback_hours: int | None = None,
        source: str | None = None,
        category: str | None = None,
        include_duplicates: bool = False,
    ) -> list[SearchResult]:
        score_expr = build_score_expression(query).label("search_score")
        stmt = select(ArticleModel, score_expr)
        for filter_expr in build_filter_expressions(query):
            stmt = stmt.where(filter_expr)
        if lookback_hours is not None:
            since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
            stmt = stmt.where(ArticleModel.published_at >= since)
        if source:
            stmt = stmt.where(ArticleModel.source_name == source)
        if category:
            stmt = stmt.where(ArticleModel.category == category)
        if not include_duplicates:
            stmt = stmt.where(ArticleModel.is_duplicate == False)
        stmt = stmt.order_by(score_expr.desc(), ArticleModel.published_at.desc(), ArticleModel.id.desc()).limit(limit)
        rows = list(self.db.execute(stmt).all())
        results: list[SearchResult] = []
        for article, sql_score in rows:
            article.ensure_utc()
            python_score, matched_fields, matched_terms = compute_python_match_metadata(article, query)
            results.append(
                SearchResult(
                    article=article,
                    score=int(sql_score if sql_score is not None else python_score),
                    matched_fields=matched_fields,
                    matched_terms=matched_terms,
                )
            )
        return results


class EventRepository:
    def __init__(self, db: Session): self.db = db

    def add(self, event: EventModel, articles: Iterable[ArticleModel] = ()) -> EventModel:
        self.db.add(event); self.db.flush()
        for article in articles: self.link_article(event.id, article.id)
        self.db.flush(); return event

    def upsert_by_day_title(self, event: EventModel, articles: Iterable[ArticleModel] = ()) -> EventModel:
        existing = self.db.execute(
            select(EventModel).where(
                EventModel.event_date == event.event_date,
                EventModel.normalized_title == event.normalized_title,
            )
        ).scalar_one_or_none()
        if existing is None:
            return self.add(event, articles)
        for name in (
            "title", "category", "severity", "first_seen_at", "last_seen_at", "article_count",
            "source_count", "trusted_source_count", "country_count", "popular_score",
            "importance_score", "breaking_score", "final_score", "status", "is_breaking",
            "breaking_detected_at", "keywords", "entities",
        ):
            setattr(existing, name, getattr(event, name))
        self.db.execute(delete(EventArticle).where(EventArticle.event_id == existing.id))
        self.db.flush()
        for article in articles:
            self.link_article(existing.id, article.id)
        self.db.flush(); return existing

    def link_article(self, event_id: int, article_id: int, relevance_score: float = 1.0) -> EventArticle:
        link = self.db.get(EventArticle, {"event_id": event_id, "article_id": article_id})
        if link is None:
            link = EventArticle(event_id=event_id, article_id=article_id, relevance_score=relevance_score)
            self.db.add(link)
        else:
            link.relevance_score = relevance_score
        self.db.flush(); return link

    def list_daily(self, date: datetime | date, limit: int = 10) -> list[EventModel]:
        event_day = date.date() if isinstance(date, datetime) else date
        return list(self.db.execute(select(EventModel).where(EventModel.event_date == event_day).order_by(EventModel.final_score.desc()).limit(limit)).scalars())

    def list_breaking(self, since_minutes: int = 180, limit: int = 20) -> list[EventModel]:
        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        return list(self.db.execute(select(EventModel).where(EventModel.is_breaking == True, EventModel.breaking_detected_at >= since).order_by(EventModel.breaking_score.desc(), EventModel.final_score.desc()).limit(limit)).scalars())


class CollectionRunRepository:
    def __init__(self, db: Session): self.db = db
    def start(self, source: str, source_type: str = "rss", lookback_hours: int | None = None) -> CollectionRun:
        run = CollectionRun(source_name=source, source_type=source_type, lookback_hours=lookback_hours, status="running"); self.db.add(run); self.db.flush(); return run
    def finish(self, run: CollectionRun, *, fetched_count: int, inserted_count: int, duplicate_count: int = 0, error: str | None = None) -> CollectionRun:
        run.finished_at = datetime.now(timezone.utc); run.fetched_count = fetched_count; run.inserted_count = inserted_count; run.duplicate_count = duplicate_count; run.error_message = error; run.error_count = 1 if error else 0; run.status = "failed" if error else "success"; self.db.flush(); return run


__all__ = ["ArticleRepository", "EventRepository", "SourceRepository", "CollectionRunRepository", "ArticleModel", "EventModel", "EventArticle", "NewsSource", "CollectionRun"]
