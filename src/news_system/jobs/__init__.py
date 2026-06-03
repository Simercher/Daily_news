from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from news_system.collectors import GDELTCollector, NewsAPICollector, NewsDataCollector, RSSCollector, ScraplingPlaywrightCollector
from news_system.collectors.sitemap_collector import SitemapCollector
from news_system.config.sources import SourceConfig, load_sources
from concurrent.futures import ThreadPoolExecutor, as_completed
from news_system.db.models import ArticleModel, EventModel
from news_system.processors.deduplicator import mark_duplicates
from news_system.processors.event_clusterer import cluster_events
from news_system.processors.event_fingerprint import generate_fingerprint
from news_system.processors.fulltext import extract_articles
from news_system.processors.fulltext_quality import compute_fulltext_quality
from news_system.processors.normalizer import normalize_title
from news_system.processors.representative_articles import select_representative
from news_system.processors.scorer import score_event, _severity_keyword_score
from news_system.processors.breaking_detector import is_breaking
from news_system.processors.breaking_alert_state import can_alert, update_alert_state
from news_system.storage.repositories import ArticleRepository, CollectionRunRepository, EventRepository, SourceRepository


def _to_model(a) -> ArticleModel:
    if isinstance(a, ArticleModel): return a
    data = a.model_dump() if hasattr(a, "model_dump") else dict(a)
    aliases = {
        "source_id": "external_id",
        "content": "content_snippet",
        "raw": "raw_payload",
        "duplicate_of_id": "duplicate_of_article_id",
    }
    for old, new in aliases.items():
        if old in data and new not in data:
            data[new] = data.pop(old)
    raw_payload = dict(data.get("raw_payload") or {})
    for compat_key in ("keywords", "entities"):
        if compat_key in data:
            raw_payload[compat_key] = data.pop(compat_key)
    data["raw_payload"] = raw_payload
    return ArticleModel(**{k: v for k, v in data.items() if k in ArticleModel.__table__.columns})


def _collector_for_source(src: SourceConfig):
    if src.source_type == "rss": collector = RSSCollector(src.url or "", source_name=src.name)
    elif src.source_type == "sitemap": collector = SitemapCollector(src.url or "", source_name=src.name)
    elif src.source_type == "newsapi":
        api_key_env = src.params.get("api_key_env") or ("NEWSAPI_API_KEY" if not src.params.get("api_key") else None)
        collector = NewsAPICollector(src.params.get("api_key"), endpoint=src.params.get("endpoint", "top-headlines"), base_url=src.base_url or "https://newsapi.org/v2", api_key_env=api_key_env)
    elif src.source_type == "gdelt": collector = GDELTCollector(base_url=src.base_url or "https://api.gdeltproject.org/api/v2/doc/doc")
    elif src.source_type == "newsdata":
        api_key_env = src.params.get("api_key_env") or "NEWSDATA_API_KEY"
        collector = NewsDataCollector(src.params.get("api_key"), base_url=src.base_url or "https://newsdata.io/api/1", api_key_env=api_key_env)
    elif src.source_type == "scrapling":
        collector = ScraplingPlaywrightCollector(src.url or "", source_name=src.name)
    elif src.source_type == "api":
        raise NotImplementedError(f"collector for '{src.name}' (type: api) not implemented yet. Set enabled: false or provide a collector.")
    else: raise ValueError(f"unsupported source_type: {src.source_type}")
    collector.source_config = src
    collector.source_name = src.name
    collector.source_type = src.source_type
    return collector


def _load_collectors(source: str = "all", config_path: str | Path = "config/sources.yaml"):
    sources = [s for s in load_sources(config_path) if s.enabled]
    if source != "all":
        source_l = source.lower()
        sources = [s for s in sources if s.source_type == source_l or s.name.lower() == source_l]
    return [_collector_for_source(s) for s in sources]


def _apply_source_metadata(article, src: SourceConfig):
    for key, value in {
        "source_type": src.source_type,
        "source_name": src.name,
        "source_domain": src.domain,
        "country": src.country,
        "category": src.category,
        "language": src.language,
    }.items():
        if value is not None:
            setattr(article, key, value)
    raw = getattr(article, "raw", None) if not isinstance(article, ArticleModel) else getattr(article, "raw_payload", None)
    if isinstance(raw, dict):
        raw.setdefault("source_config", {
            "trusted": src.trusted,
            "credibility_score": src.credibility_score,
            "priority": src.priority,
            "source_type": src.source_type,
            "name": src.name,
        })


def collect_job(db: Session | None = None, source: str = "all", lookback_hours: int = 1, collectors=None, config_path: str | Path = "config/sources.yaml"):
    """Collect enabled sources, normalize/dedupe, upsert articles, and return JSON-safe stats."""
    collectors = collectors if collectors is not None else _load_collectors(source, config_path)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    owns_db = db is None
    if owns_db:
        from news_system.db.models import Base
        from news_system.db.session import get_engine, get_session_local
        engine = get_engine()
        Base.metadata.create_all(engine)
        db = get_session_local()()

    assert db is not None
    run_repo = CollectionRunRepository(db)
    article_repo = ArticleRepository(db)
    source_repo = SourceRepository(db)
    stats = {"fetched": 0, "inserted": 0, "duplicates": 0, "filtered_old": 0, "source_counts": {}, "errors": []}
    raw_by_source: list[tuple[str, object]] = []
    runs = []
    try:
        # ── Parallel collection ─────────────────────────────────────
        MAX_WORKERS = 8
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {}
            for c in collectors:
                src_cfg = getattr(c, "source_config", None)
                name = getattr(c, "source_name", None) or c.__class__.__name__
                source_type = getattr(c, "source_type", c.__class__.__name__.replace("Collector", "").lower() or "rss")
                stats["source_counts"][name] = {"fetched": 0, "inserted": 0, "duplicates": 0, "filtered_old": 0, "errors": 0}
                if src_cfg:
                    source_repo.upsert(name=src_cfg.name, source_type=src_cfg.source_type, url=src_cfg.url, domain=src_cfg.domain, country=src_cfg.country, language=src_cfg.language, category=src_cfg.category, trusted=src_cfg.trusted, enabled=src_cfg.enabled, priority=src_cfg.priority)
                run = run_repo.start(name, source_type=source_type, lookback_hours=lookback_hours)
                runs.append((run, name))
                params = dict(getattr(src_cfg, "params", {}) or {}) if src_cfg else {}
                if src_cfg and src_cfg.query:
                    params.setdefault("q" if src_cfg.source_type == "newsapi" else "query", src_cfg.query)
                futures[pool.submit(c.fetch, lookback_hours=lookback_hours, **params)] = (name, run, src_cfg)

            for future in as_completed(futures):
                name, run, src_cfg = futures[future]
                error = None
                fetched = filtered_old = 0
                try:
                    items = future.result() or []
                    fetched = len(items)
                    stats["fetched"] += fetched
                    stats["source_counts"][name]["fetched"] = fetched
                    if src_cfg:
                        for item in items:
                            _apply_source_metadata(item, src_cfg)
                    for item in items:
                        model = _to_model(item)
                        model.ensure_utc()
                        if model.published_at < cutoff:
                            filtered_old += 1
                            continue
                        raw_by_source.append((name, model))
                except Exception as exc:
                    error = str(exc)
                    stats["errors"].append({"source": name, "error": error})
                    stats["source_counts"][name]["errors"] = 1
                stats["filtered_old"] += filtered_old
                stats["source_counts"][name]["filtered_old"] = filtered_old
                run_repo.finish(run, fetched_count=fetched, inserted_count=0, duplicate_count=0, error=error)

        # Extract full text for articles that lack content
        all_articles = [a for _, a in raw_by_source]
        extract_articles(all_articles)

        # Compute fulltext_quality_score for each article
        now = datetime.now(timezone.utc)
        for a in all_articles:
            content = getattr(a, "content_snippet", None) or getattr(a, "content", None)
            fts = getattr(a, "fulltext_status", None) or "not_attempted"
            if fts == "extracted" and content:
                quality, _ = compute_fulltext_quality(content, status="extracted")
                a.fulltext_quality_score = quality
                a.fulltext_extracted_at = now

        marked = mark_duplicates(all_articles)
        # Two-pass upsert: first insert all originals, then set duplicate refs
        article_map = {}  # index_in_list -> db_id
        dup_indices = {}  # index_in_list -> dup_of_index
        
        for idx, ((name, _), article) in enumerate(zip(raw_by_source, marked)):
            dup_ref = getattr(article, "duplicate_of_article_id", None)
            if dup_ref is not None and isinstance(dup_ref, int) and dup_ref < len(marked):
                dup_indices[idx] = dup_ref
                article.duplicate_of_article_id = None

            _, was_inserted = article_repo.upsert(article)
            article_map[idx] = getattr(article, "id", None) or 0

            if was_inserted:
                stats["inserted"] += 1
                stats["source_counts"][name]["inserted"] += 1
            else:
                stats["duplicates"] += 1
                stats["source_counts"][name]["duplicates"] += 1

        # Second pass: set duplicate_of_article_id using no_autoflush
        # to avoid premature flush of pending changes
        db.commit()  # commit first pass so all originals are persisted
        with db.no_autoflush:
            for idx, ((name, _), article) in enumerate(zip(raw_by_source, marked)):
                dup_of_idx = dup_indices.get(idx)
                if dup_of_idx is not None:
                    orig_db_id = article_map.get(dup_of_idx)
                    if orig_db_id and orig_db_id != getattr(article, "id", None):
                        article.duplicate_of_article_id = orig_db_id
                        try:
                            article_repo.upsert(article)
                        except Exception:
                            pass

        for run, name in runs:
            sc = stats["source_counts"].get(name, {})
            run.inserted_count = sc.get("inserted", 0)
            run.duplicate_count = sc.get("duplicates", 0)
        db.commit()
        return stats
    finally:
        if owns_db:
            db.close()


BREAKING_CATEGORIES = {"war_conflict", "disaster", "politics", "economy", "health"}
EXTREME_BREAKING_CATEGORIES = {"war_conflict", "disaster"}


def _source_key(article) -> str | None:
    return getattr(article, "source_name", None) or getattr(article, "source_domain", None) or getattr(article, "external_id", None)


def _is_trusted_source(article) -> bool:
    raw = getattr(article, "raw_payload", None) or {}
    cfg = raw.get("source_config") if isinstance(raw, dict) else None
    if isinstance(cfg, dict):
        # Check credibility_score first (>= 0.75 means trusted)
        cred = cfg.get("credibility_score")
        if cred is not None:
            return float(cred) >= 0.75
        # Fallback to trusted boolean
        if cfg.get("trusted") is not None:
            return bool(cfg.get("trusted"))
    # Backward compatibility for legacy data/tests without source_config metadata:
    # unknown sources are usable; explicit trusted=False still blocks.
    return True


def _event_category(articles) -> str | None:
    counts = Counter(getattr(a, "category", None) for a in articles if getattr(a, "category", None))
    if counts:
        return counts.most_common(1)[0][0]
    text = " ".join(
        " ".join([
            getattr(a, "title", "") or "",
            getattr(a, "description", "") or "",
            " ".join(getattr(a, "keywords", []) or []),
        ]).lower()
        for a in articles
    )
    if any(term in text for term in ("earthquake", "quake", "flood", "hurricane", "wildfire", "disaster")):
        return "disaster"
    if any(term in text for term in ("war", "attack", "missile", "invasion", "conflict")):
        return "war_conflict"
    return None


def _breaking_score(ev, trusted_source_count: int, recent_article_count: int, severity_keyword_score: float) -> float:
    # Practical Step 5 score from the simplified scorer fields plus source trust.
    source_component = min(1.0, trusted_source_count / 2.0)
    article_component = min(1.0, recent_article_count / 3.0)
    return round(max(getattr(ev, "final_score", 0.0), 0.4 * severity_keyword_score + 0.3 * source_component + 0.3 * article_component), 4)


def _apply_breaking_rules(ev, *, category: str | None, trusted_source_count: int, recent_article_count: int, severity_keyword_score: float, breaking_score: float) -> bool:
    normal = (
        breaking_score >= 0.75
        and trusted_source_count >= 2
        and recent_article_count >= 3
        and category in BREAKING_CATEGORIES
    )
    relaxed = (
        category in EXTREME_BREAKING_CATEGORIES
        and trusted_source_count >= 1
        and recent_article_count >= 2
        and severity_keyword_score >= 0.4
    )
    return normal or relaxed


def _persist_events(db: Session, events) -> list[EventModel]:
    repo = EventRepository(db); out = []
    for ev in events:
        event_dt = max((a.published_at for a in ev.articles), default=datetime.now(timezone.utc))
        sources = {_source_key(a) for a in ev.articles if _source_key(a)}
        trusted_sources = {_source_key(a) for a in ev.articles if _source_key(a) and _is_trusted_source(a)}
        category = getattr(ev, "category", None) or _event_category(ev.articles)
        breaking_detected_at = datetime.now(timezone.utc) if getattr(ev, "is_breaking", False) else None

        # Generate event fingerprint
        entities_list = list(getattr(ev, "entities", set()) or [])
        keywords_list = list(getattr(ev, "keywords", set()) or [])
        # Get first article for collected_at, source_country, etc.
        first_article = ev.articles[0] if ev.articles else None
        collected_at = getattr(first_article, "collected_at", None) if first_article else None
        source_country = getattr(first_article, "country", None) if first_article else None
        normalized_title = getattr(ev, "normalized_title", None) or normalize_title(ev.title)
        fingerprint = generate_fingerprint(
            category=category,
            dt=event_dt,
            collected_at=collected_at,
            entities=entities_list,
            keywords=keywords_list,
            source_country=source_country,
            normalized_title=normalized_title,
        )

        # Select representative article
        best_article_id, representative_list = select_representative(ev.articles)

        # Compute credibility-based trusted_source_count
        credibility_trusted = {
            _source_key(a) for a in ev.articles
            if _source_key(a) and _is_trusted_source(a)
        }

        # Get score_breakdown from scorer if available
        score_breakdown = getattr(ev, "score_breakdown", None)
        if score_breakdown is None:
            score_breakdown = {}

        model = EventModel(
            title=ev.title,
            normalized_title=getattr(ev, "normalized_title", None) or normalize_title(ev.title),
            event_date=event_dt.date(),
            first_seen_at=min((a.published_at for a in ev.articles), default=event_dt),
            last_seen_at=event_dt,
            keywords=list(ev.keywords),
            entities=ev.entities if isinstance(getattr(ev, "entities", {}), dict) else {"items": list(ev.entities)},
            category=category,
            article_count=len(ev.articles),
            source_count=len(sources),
            trusted_source_count=len(credibility_trusted),
            country_count=len({getattr(a, "country", None) for a in ev.articles if getattr(a, "country", None)}),
            popular_score=ev.source_diversity_score,
            importance_score=ev.severity_score,
            breaking_score=getattr(ev, "breaking_score", ev.velocity_score),
            final_score=ev.final_score,
            status="active",
            is_breaking=getattr(ev, "is_breaking", False),
            breaking_detected_at=breaking_detected_at,
            event_fingerprint=fingerprint,
            score_breakdown=score_breakdown,
            representative_article_id=best_article_id,
            last_scored_at=getattr(ev, "last_scored_at", None),
            cluster_method="fingerprint+title+keyword",
        )
        persisted = repo.upsert_by_day_title(model, ev.articles)

        # Update the persisted event with new fields that upsert_by_day_title may not set
        if persisted:
            persisted.event_fingerprint = fingerprint
            persisted.score_breakdown = score_breakdown
            persisted.representative_article_id = best_article_id
            persisted.last_scored_at = getattr(ev, "last_scored_at", None)
            persisted.cluster_method = "fingerprint+title+keyword"

        out.append(persisted)
    db.commit(); return out


def daily_event_job(db: Session | None = None, lookback_hours: int = 24, limit: int = 10, *, articles: Iterable | None = None):
    if articles is None and db:
        articles = ArticleRepository(db).list_recent(hours=lookback_hours, include_duplicates=False)
    events = [score_event(e) for e in cluster_events(list(articles or []))]
    events = sorted(events, key=lambda e: e.final_score, reverse=True)[:limit]
    return _persist_events(db, events) if db else events


def breaking_watch_job(db: Session | None = None, since_minutes: int = 60, limit: int = 20, *, articles: Iterable | None = None):
    if articles is None and db:
        hours = max(1, (since_minutes + 59) // 60)
        since = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        articles = [a for a in ArticleRepository(db).list_recent(hours=hours, include_duplicates=False) if a.published_at >= since]
    events = []
    for ev in [score_event(e) for e in cluster_events(list(articles or []))]:
        category = _event_category(ev.articles)
        # Use credibility_score >= 0.75 for trusted source counting
        trusted_count = len({
            _source_key(a) for a in ev.articles
            if _source_key(a) and _is_trusted_source(a)
        })
        recent_count = len(ev.articles)
        severity = getattr(ev, "severity_score", 0.0)
        sev_kw_score = _severity_keyword_score(ev.articles)
        ev.category = category
        ev.breaking_score = _breaking_score(ev, trusted_count, recent_count, sev_kw_score)
        ev.is_breaking = _apply_breaking_rules(
            ev,
            category=category,
            trusted_source_count=trusted_count,
            recent_article_count=recent_count,
            severity_keyword_score=sev_kw_score,
            breaking_score=ev.breaking_score,
        )
        if ev.is_breaking: events.append(ev)
    events = sorted(events, key=lambda e: (getattr(e, "breaking_score", 0.0), getattr(e, "final_score", 0.0)), reverse=True)[:limit]
    return _persist_events(db, events) if db else events