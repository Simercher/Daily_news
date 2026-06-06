from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Auto-load repo .env BEFORE any project imports so DATABASE_URL is set
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

from news_system.config.sources import SourceConfigError, load_sources
from news_system.db.models import ArticleModel, EventArticle, EventModel
from news_system.db.schema import prepare_schema
from news_system.db.session import get_engine, get_session_local
from news_system.jobs import collect_job, daily_event_job, breaking_watch_job
from news_system.processors.event_fingerprint import generate_fingerprint
from news_system.processors.fulltext import extract_articles
from news_system.processors.fulltext_quality import compute_fulltext_quality
from news_system.processors.representative_articles import select_representative
from news_system.processors.scorer import score_event
from news_system.serializers import events_payload, search_query_plan_to_dict, search_result_to_dict
from news_system.search.query_parser import SearchQueryError, parse_search_query
from news_system.storage.repositories import ArticleRepository, EventRepository
from news_system.storage.smoke import run_db_smoke
from sqlalchemy import delete, select, update


def _json(data):
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))


def _prepare_schema_for_cli(engine) -> None:
    prepare_schema(engine, usage="the daily-news CLI")


def _session():
    engine = get_engine()
    _prepare_schema_for_cli(engine)
    return get_session_local()()


def _validate_search_args(args) -> str | None:
    if args.limit <= 0:
        return "--limit must be a positive integer"
    if args.lookback_hours < 0:
        return "--lookback-hours must be zero or greater"
    if not args.query.strip():
        return "query must not be blank"
    return None


def main(argv=None):
    p = argparse.ArgumentParser(prog="daily-news")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect")
    c.add_argument("--source", default="all")
    c.add_argument("--lookback-hours", type=int, default=1)
    c.add_argument("--config", default="config/sources.yaml")

    sources_p = sub.add_parser("sources")
    sources_sub = sources_p.add_subparsers(dest="sources_cmd", required=True)
    sl = sources_sub.add_parser("list")
    sl.add_argument("--config", default="config/sources.yaml")
    sv = sources_sub.add_parser("validate")
    sv.add_argument("--config", default="config/sources.yaml")

    build = sub.add_parser("build-events")
    build.add_argument("--lookback-hours", type=int, default=24)
    build.add_argument("--limit", type=int, default=10)

    watch = sub.add_parser("watch-breaking")
    watch.add_argument("--lookback-minutes", type=int, default=60)
    watch.add_argument("--limit", type=int, default=20)

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--lookback-hours", type=int, default=24)
    search.add_argument("--source", type=str, default=None)
    search.add_argument("--category", type=str, default=None)
    search.add_argument("--include-duplicates", action="store_true", default=False)

    show_daily = sub.add_parser("show-daily")
    show_daily.add_argument("--date", required=True)
    show_daily.add_argument("--limit", type=int, default=10)

    show_breaking = sub.add_parser("show-breaking")
    show_breaking.add_argument("--since-minutes", type=int, default=180)
    show_breaking.add_argument("--limit", type=int, default=20)
    sub.add_parser("db-smoke")

    # --- v1.1 commands ---
    extract_ft = sub.add_parser("extract-fulltext")
    extract_ft.add_argument("--article-id", type=int, default=None)
    extract_ft.add_argument("--source", type=str, default=None)
    extract_ft.add_argument("--status", type=str, default=None)
    extract_ft.add_argument("--lookback-hours", type=int, default=24)
    extract_ft.add_argument("--only-missing", action="store_true", default=False)

    score_ev = sub.add_parser("score-event")
    score_ev.add_argument("--event-id", type=int, required=True)

    merge_ev = sub.add_parser("merge-events")
    merge_ev.add_argument("--source-event-id", type=int, required=True)
    merge_ev.add_argument("--target-event-id", type=int, required=True)

    split_ev = sub.add_parser("split-event")
    split_ev.add_argument("--event-id", type=int, required=True)
    split_ev.add_argument("--article-ids", type=str, required=True)

    args = p.parse_args(argv)

    try:
        if args.cmd == "collect":
            result = collect_job(source=args.source, lookback_hours=args.lookback_hours, config_path=args.config)
            _json(result)
        elif args.cmd == "sources":
            sources = load_sources(args.config)
            if args.sources_cmd == "validate":
                _json({"ok": True, "source_count": len(sources), "enabled_count": sum(1 for s in sources if s.enabled)})
            else:
                fields = ("enabled", "trusted", "source_type", "priority", "name", "category", "country", "language", "url", "query", "domain", "base_url")
                _json([{k: s.to_dict().get(k) for k in fields} for s in sources])
        elif args.cmd == "build-events":
            db = _session()
            try:
                events = daily_event_job(db, lookback_hours=args.lookback_hours, limit=args.limit)
                _json(events_payload(events, lookback_hours=args.lookback_hours, limit=args.limit))
            finally:
                db.close()
        elif args.cmd == "show-daily":
            event_date = date_type.fromisoformat(args.date)
            db = _session()
            try:
                events = EventRepository(db).list_daily(event_date, limit=args.limit)
                _json(events_payload(events, date=args.date, limit=args.limit))
            finally:
                db.close()
        elif args.cmd == "db-smoke":
            _json(run_db_smoke())
        elif args.cmd == "watch-breaking":
            db = _session()
            try:
                events = breaking_watch_job(db, since_minutes=args.lookback_minutes, limit=args.limit)
                _json(events_payload(events, lookback_minutes=args.lookback_minutes, limit=args.limit))
            finally:
                db.close()
        elif args.cmd == "search":
            validation_error = _validate_search_args(args)
            if validation_error:
                _json({"cmd": "search", "error": validation_error})
                return
            try:
                parsed_query = parse_search_query(args.query)
            except SearchQueryError as exc:
                _json({"cmd": "search", "error": str(exc)})
                return
            db = _session()
            try:
                results = ArticleRepository(db).search_parsed(
                    parsed_query,
                    limit=args.limit,
                    lookback_hours=args.lookback_hours,
                    source=args.source,
                    category=args.category,
                    include_duplicates=args.include_duplicates,
                )
                payload_articles = [search_result_to_dict(result) for result in results]
                _json({
                    "cmd": "search",
                    "query": args.query,
                    "lookback_hours": args.lookback_hours,
                    "limit": args.limit,
                    "source": args.source,
                    "category": args.category,
                    "include_duplicates": args.include_duplicates,
                    "query_plan": search_query_plan_to_dict(parsed_query),
                    "count": len(payload_articles),
                    "articles": payload_articles,
                })
            finally:
                db.close()
        elif args.cmd == "show-breaking":
            db = _session()
            try:
                events = EventRepository(db).list_breaking(since_minutes=args.since_minutes, limit=args.limit)
                _json(events_payload(events, since_minutes=args.since_minutes, limit=args.limit))
            finally:
                db.close()

        # --- v1.1 command handlers ---
        elif args.cmd == "extract-fulltext":
            db = _session()
            try:
                now = datetime.now(timezone.utc)
                query = select(ArticleModel)

                if args.article_id is not None:
                    # Single article by ID — ignore other filters
                    query = query.where(ArticleModel.id == args.article_id)
                else:
                    since = now - timedelta(hours=args.lookback_hours)
                    query = query.where(ArticleModel.published_at >= since)

                    if args.source:
                        query = query.where(ArticleModel.source_name == args.source)

                    if args.status:
                        query = query.where(ArticleModel.fulltext_status == args.status)

                    if args.only_missing:
                        query = query.where(
                            (ArticleModel.content_snippet == None)
                            | (ArticleModel.content_snippet == "")
                            | (ArticleModel.content_snippet == "ONLY AVAILABLE IN PAID PLANS")
                        )

                articles = list(db.execute(query).scalars())
                total = len(articles)

                # Run extraction (modifies articles in-place)
                extract_articles(articles)

                # Compute quality scores and finalize per-article fields
                extracted = 0
                skipped = 0
                errors = 0
                for a in articles:
                    fts = a.fulltext_status
                    if fts == "extracted":
                        quality, _ = compute_fulltext_quality(
                            a.content_snippet, status="extracted"
                        )
                        a.fulltext_quality_score = quality
                        a.fulltext_extracted_at = now
                        extracted += 1
                    elif fts in ("error", "timeout"):
                        quality, _ = compute_fulltext_quality(
                            a.content_snippet, status=fts
                        )
                        a.fulltext_quality_score = quality
                        a.fulltext_extracted_at = now
                        errors += 1
                    else:
                        skipped += 1

                db.commit()
                _json({
                    "cmd": "extract-fulltext",
                    "total": total,
                    "extracted": extracted,
                    "skipped": skipped,
                    "errors": errors,
                })
            finally:
                db.close()

        elif args.cmd == "score-event":
            db = _session()
            try:
                event = db.get(EventModel, args.event_id)
                if event is None:
                    _json({"error": f"event {args.event_id} not found"})
                    return

                # Load articles linked to this event
                stmt = (
                    select(ArticleModel)
                    .join(EventArticle, ArticleModel.id == EventArticle.article_id)
                    .where(EventArticle.event_id == args.event_id)
                )
                articles = list(db.execute(stmt).scalars())

                # Attach articles to the event model so score_event can read them
                event.articles = articles

                # Regenerate event fingerprint
                entities_list = list(event.entities or {})
                if isinstance(entities_list, dict):
                    entities_list = list(entities_list.keys())
                keywords_list = list(event.keywords or [])
                event.event_fingerprint = generate_fingerprint(
                    category=event.category,
                    dt=event.first_seen_at,
                    entities=entities_list,
                    keywords=keywords_list,
                )

                # Select representative article
                best_id, _ = select_representative(articles)
                event.representative_article_id = best_id

                # Score the event
                score_event(event)

                event.last_scored_at = datetime.now(timezone.utc)
                db.commit()

                _json({
                    "cmd": "score-event",
                    "event_id": event.id,
                    "popular_score": event.popular_score,
                    "importance_score": event.importance_score,
                    "breaking_score": event.breaking_score,
                    "final_score": event.final_score,
                    "score_breakdown": event.score_breakdown,
                    "article_count": len(articles),
                })
            finally:
                db.close()

        elif args.cmd == "merge-events":
            db = _session()
            try:
                source = db.get(EventModel, args.source_event_id)
                target = db.get(EventModel, args.target_event_id)
                if source is None:
                    _json({"error": f"source event {args.source_event_id} not found"})
                    return
                if target is None:
                    _json({"error": f"target event {args.target_event_id} not found"})
                    return

                # Move all EventArticle links from source to target
                links = list(
                    db.execute(
                        select(EventArticle).where(
                            EventArticle.event_id == args.source_event_id
                        )
                    ).scalars()
                )
                moved_count = 0
                for link in links:
                    existing = db.get(
                        EventArticle,
                        {"event_id": args.target_event_id, "article_id": link.article_id},
                    )
                    if existing is None:
                        new_link = EventArticle(
                            event_id=args.target_event_id,
                            article_id=link.article_id,
                            relevance_score=link.relevance_score,
                        )
                        db.add(new_link)
                        moved_count += 1

                # Set source event status to merged and record merged_into_event_id
                source.status = "merged"
                source_entities = dict(source.entities or {})
                source_entities["merged_into_event_id"] = args.target_event_id
                source.entities = source_entities
                db.flush()

                # Re-score target event
                stmt = (
                    select(ArticleModel)
                    .join(EventArticle, ArticleModel.id == EventArticle.article_id)
                    .where(EventArticle.event_id == args.target_event_id)
                )
                articles = list(db.execute(stmt).scalars())
                target.articles = articles
                target.article_count = len(articles)

                entities_list = list(target.entities or {})
                if isinstance(entities_list, dict):
                    entities_list = list(entities_list.keys())
                keywords_list = list(target.keywords or [])
                target.event_fingerprint = generate_fingerprint(
                    category=target.category,
                    dt=target.first_seen_at,
                    entities=entities_list,
                    keywords=keywords_list,
                )
                best_id, _ = select_representative(articles)
                target.representative_article_id = best_id
                score_event(target)
                target.last_scored_at = datetime.now(timezone.utc)
                db.commit()

                _json({
                    "cmd": "merge-events",
                    "source_event_id": args.source_event_id,
                    "target_event_id": args.target_event_id,
                    "moved_articles": moved_count,
                    "target_article_count": target.article_count,
                    "final_score": target.final_score,
                })
            finally:
                db.close()

        elif args.cmd == "split-event":
            db = _session()
            try:
                source_event = db.get(EventModel, args.event_id)
                if source_event is None:
                    _json({"error": f"event {args.event_id} not found"})
                    return

                try:
                    split_ids = [
                        int(x.strip()) for x in args.article_ids.split(",") if x.strip()
                    ]
                except ValueError:
                    _json({"error": "invalid --article-ids; must be comma-separated integers"})
                    return

                if not split_ids:
                    _json({"error": "no article IDs provided"})
                    return

                # Verify all article IDs actually belong to this event
                existing_links = list(
                    db.execute(
                        select(EventArticle).where(
                            EventArticle.event_id == args.event_id,
                            EventArticle.article_id.in_(split_ids),
                        )
                    ).scalars()
                )
                found_ids = {l.article_id for l in existing_links}
                missing = [aid for aid in split_ids if aid not in found_ids]
                if missing:
                    _json({
                        "error": f"articles {missing} not found in event {args.event_id}",
                    })
                    return

                # Load the articles being split off
                split_articles = list(
                    db.execute(
                        select(ArticleModel).where(ArticleModel.id.in_(split_ids))
                    ).scalars()
                )

                # Remove article links from source event
                db.execute(
                    delete(EventArticle).where(
                        EventArticle.event_id == args.event_id,
                        EventArticle.article_id.in_(split_ids),
                    )
                )
                db.flush()

                # Create new event for the split articles
                event_date = (
                    max(a.published_at for a in split_articles).date()
                    if split_articles
                    else source_event.event_date
                )
                title = split_articles[0].title if split_articles else source_event.title
                new_event = EventModel(
                    title=title,
                    normalized_title=split_articles[0].normalized_title if split_articles else source_event.normalized_title,
                    event_date=event_date,
                    category=source_event.category,
                    status="active",
                    keywords=list(source_event.keywords or []),
                    entities=dict(source_event.entities or {}),
                )
                db.add(new_event)
                db.flush()

                # Link split articles to new event
                for aid in split_ids:
                    link = EventArticle(
                        event_id=new_event.id,
                        article_id=aid,
                        relevance_score=1.0,
                    )
                    db.add(link)
                db.flush()

                # Re-score both events
                source_articles = list(
                    db.execute(
                        select(ArticleModel)
                        .join(EventArticle, ArticleModel.id == EventArticle.article_id)
                        .where(EventArticle.event_id == args.event_id)
                    ).scalars()
                )
                source_event.articles = source_articles
                source_event.article_count = len(source_articles)
                entities_list = list(source_event.entities or {})
                if isinstance(entities_list, dict):
                    entities_list = list(entities_list.keys())
                keywords_list = list(source_event.keywords or [])
                source_event.event_fingerprint = generate_fingerprint(
                    category=source_event.category,
                    dt=source_event.first_seen_at,
                    entities=entities_list,
                    keywords=keywords_list,
                )
                best_id, _ = select_representative(source_articles)
                source_event.representative_article_id = best_id
                score_event(source_event)
                source_event.last_scored_at = datetime.now(timezone.utc)

                new_event.articles = split_articles
                new_event.article_count = len(split_articles)
                entities_list2 = list(new_event.entities or {})
                if isinstance(entities_list2, dict):
                    entities_list2 = list(entities_list2.keys())
                keywords_list2 = list(new_event.keywords or [])
                new_event.event_fingerprint = generate_fingerprint(
                    category=new_event.category,
                    dt=new_event.first_seen_at or event_date,
                    entities=entities_list2,
                    keywords=keywords_list2,
                )
                best_id2, _ = select_representative(split_articles)
                new_event.representative_article_id = best_id2
                score_event(new_event)
                new_event.last_scored_at = datetime.now(timezone.utc)

                db.commit()

                _json({
                    "cmd": "split-event",
                    "source_event_id": args.event_id,
                    "new_event_id": new_event.id,
                    "split_article_count": len(split_ids),
                    "source_article_count": source_event.article_count,
                    "source_final_score": source_event.final_score,
                    "new_event_final_score": new_event.final_score,
                })
            finally:
                db.close()

    except SourceConfigError as exc:
        print(f"source config error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()