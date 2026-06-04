#!/usr/bin/env python3
"""
Domain classifier + summarizer script.

Reads articles from PostgreSQL, classifies by domain, groups them,
and outputs structured JSON for downstream Discord posting. Production
classification here is deterministic/rule-based only; the news-briefing-writer
Hermes profile/sub-agent may use the emitted rule_domain metadata as a
reference for final LLM reasoning.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# Auto-load repo .env and shared /opt/data/.env BEFORE any project imports.
# setdefault preserves already-set environment variables.
def _load_env_files() -> None:
    repo_env = Path(__file__).resolve().parent.parent / ".env"
    shared_env = Path("/opt/data/.env")
    for env_path in (repo_env, shared_env):
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, val)


_load_env_files()

# isort: skip  — project imports must come after .env loading
from news_system.db.models import ArticleModel, Base  # noqa: E402
from news_system.db.session import get_engine, get_session_local  # noqa: E402
from news_system.processors.domain_summarizer import (  # noqa: E402
    ClassificationDecision,
    build_domain_summaries,
    classify_articles_with_decisions,
)

from sqlalchemy import select  # noqa: E402


def _decision_metadata(decisions: dict[str, ClassificationDecision]) -> dict[str, Any]:
    method_counts: dict[str, int] = {}
    items: dict[str, dict[str, Any]] = {}
    for article_id, decision in decisions.items():
        method_counts[decision.method] = method_counts.get(decision.method, 0) + 1
        item = {
            "index": decision.index,
            "domain": decision.domain,
            "method": decision.method,
            "rule_domain": decision.rule_domain,
        }
        if decision.confidence is not None:
            item["confidence"] = decision.confidence
        if decision.reason:
            item["reason"] = str(decision.reason)[:180]
        items[str(article_id)] = item
    return {"method_counts": method_counts, "decisions": items}


def main():
    p = argparse.ArgumentParser(prog="domain-summarizer")
    p.add_argument("--lookback-hours", type=int, default=24)
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()

    engine = get_engine()
    Base.metadata.create_all(engine)
    db = get_session_local()()

    try:
        since = datetime.now(timezone.utc) - timedelta(hours=args.lookback_hours)

        stmt = (
            select(ArticleModel)
            .where(ArticleModel.published_at >= since)
            .where(ArticleModel.is_duplicate == False)
            .order_by(ArticleModel.published_at.desc())
        )
        if args.limit is not None:
            stmt = stmt.limit(args.limit)

        articles = list(db.execute(stmt).scalars())

        # Production script intentionally performs no external LLM/API calls.
        # The processor still supports injectable LLM helpers for unit tests and
        # non-production callers, but this script emits rule metadata only so the
        # news-briefing-writer Hermes profile can make the final LLM judgement.
        classified, decisions = classify_articles_with_decisions(articles)
        summaries = build_domain_summaries(classified)

        total = sum(s["count"] for s in summaries.values())
        decision_meta = _decision_metadata(decisions)

        payload = {
            "ok": True,
            "cmd": "domain-summarizer",
            "total_articles": total,
            "lookback_hours": args.lookback_hours,
            "queried_articles": len(articles),
            "classification": {
                "method": "rule",
                "description": (
                    "deterministic rule-based grouping; rule_domain is provided "
                    "as reference for news-briefing-writer final classification"
                ),
                **decision_meta,
            },
            "domains": summaries,
        }

        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0

    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "cmd": "domain-summarizer",
            "error": str(exc),
        }, ensure_ascii=False))
        return 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
