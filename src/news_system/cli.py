import argparse
import json

from news_system.jobs import collect_job, daily_event_job, breaking_watch_job
from news_system.storage.smoke import run_db_smoke


def main(argv=None):
    p = argparse.ArgumentParser(prog="daily-news")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--source", default="all")
    c.add_argument("--lookback-hours", type=int, default=1)
    sub.add_parser("build-events")
    sub.add_parser("watch-breaking")
    sub.add_parser("show-daily")
    sub.add_parser("show-breaking")
    sub.add_parser("db-smoke")
    args = p.parse_args(argv)
    if args.cmd == "collect":
        print(json.dumps({"articles": len(collect_job(args.source, args.lookback_hours))}))
    elif args.cmd in ("build-events", "show-daily"):
        print(json.dumps({"events": len(daily_event_job([]))}))
    elif args.cmd == "db-smoke":
        print(json.dumps(run_db_smoke(), sort_keys=True))
    else:
        print(json.dumps({"breaking": len(breaking_watch_job([]))}))


if __name__ == "__main__":
    main()
