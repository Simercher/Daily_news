from __future__ import annotations

import argparse
import json
import sys
from datetime import date as date_type

from news_system.config.sources import SourceConfigError, load_sources
from news_system.db.models import Base
from news_system.db.session import get_engine, get_session_local
from news_system.jobs import collect_job, daily_event_job, breaking_watch_job
from news_system.serializers import events_payload
from news_system.storage.repositories import EventRepository
from news_system.storage.smoke import run_db_smoke


def _json(data):
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))


def _session():
    engine = get_engine()
    Base.metadata.create_all(engine)
    return get_session_local()()


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

    show_daily = sub.add_parser("show-daily")
    show_daily.add_argument("--date", required=True)
    show_daily.add_argument("--limit", type=int, default=10)

    show_breaking = sub.add_parser("show-breaking")
    show_breaking.add_argument("--since-minutes", type=int, default=180)
    show_breaking.add_argument("--limit", type=int, default=20)
    sub.add_parser("db-smoke")
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
        elif args.cmd == "show-breaking":
            db = _session()
            try:
                events = EventRepository(db).list_breaking(since_minutes=args.since_minutes, limit=args.limit)
                _json(events_payload(events, since_minutes=args.since_minutes, limit=args.limit))
            finally:
                db.close()
    except SourceConfigError as exc:
        print(f"source config error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
