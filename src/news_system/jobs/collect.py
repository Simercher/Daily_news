from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from news_system.collectors import GDELTCollector, NewsAPICollector, NewsDataCollector, RSSCollector, ScraplingPlaywrightCollector
from news_system.collectors.sitemap_collector import SitemapCollector
from news_system.config.sources import SourceConfig, load_sources
from news_system.db.models import ArticleModel
from news_system.processors.deduplicator import mark_duplicates
from news_system.processors.fulltext import extract_articles
from news_system.processors.fulltext_quality import compute_fulltext_quality
from news_system.storage.repositories import ArticleRepository, CollectionRunRepository, SourceRepository

from .shared import _to_model


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

        all_articles = [a for _, a in raw_by_source]
        extract_articles(all_articles)

        now = datetime.now(timezone.utc)
        for a in all_articles:
            content = getattr(a, "content_snippet", None) or getattr(a, "content", None)
            fts = getattr(a, "fulltext_status", None) or "not_attempted"
            if fts == "extracted" and content:
                quality, _ = compute_fulltext_quality(content, status="extracted")
                a.fulltext_quality_score = quality
                a.fulltext_extracted_at = now

        marked = mark_duplicates(all_articles)
        article_map = {}
        dup_indices = {}

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

        db.commit()
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
