#!/usr/bin/env python3
"""
Quick RSS-only collection for breaking news monitoring.
Collects only RSS sources (no scrapling/playwright) for fast turnaround.

Usage:
    uv run python scripts/collect_rss_quick.py --lookback-hours 2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

from news_system.collectors import RSSCollector  # noqa: E402
from news_system.config.sources import load_sources  # noqa: E402
from news_system.db.models import Base  # noqa: E402
from news_system.db.session import get_engine, get_session_local  # noqa: E402
from news_system.jobs import collect_job  # noqa: E402


def main():
    p = argparse.ArgumentParser(prog="collect-rss-quick")
    p.add_argument("--lookback-hours", type=int, default=2)
    args = p.parse_args()

    engine = get_engine()
    Base.metadata.create_all(engine)
    db = get_session_local()()

    try:
        srcs = [
            s
            for s in load_sources("config/sources.yaml")
            if s.enabled and s.source_type == "rss"
        ]
        collectors = []
        for s in srcs:
            c = RSSCollector(s.url or "", source_name=s.name)
            c.source_config = s
            c.source_name = s.name
            c.source_type = "rss"
            collectors.append(c)

        result = collect_job(
            db=db, source="rss", lookback_hours=args.lookback_hours, collectors=collectors
        )
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())