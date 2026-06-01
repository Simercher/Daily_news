from __future__ import annotations

import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from dateutil import parser as date_parser
from pydantic import BaseModel

from .config import resolve_path

USER_AGENT = "news_feed_bootstrap/0.1 (+https://example.local; respectful RSS collector)"
TIMEOUT = float(os.getenv("NEWS_FEED_TIMEOUT_SECONDS", "15"))


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        parsed = date_parser.parse(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def is_blocked_response(status_code: int | None, text: str = "") -> bool:
    if status_code in {401, 403, 429}:
        return True
    lowered = text[:5000].lower()
    return any(marker in lowered for marker in ("cloudflare", "access denied", "captcha", "verify you are human"))


def write_jsonl(path: str | Path, rows: Iterable[BaseModel | dict]) -> None:
    resolved = resolve_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("w", encoding="utf-8") as fh:
        for row in rows:
            payload = row.model_dump(mode="json") if isinstance(row, BaseModel) else row
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_json(path: str | Path, data: object) -> None:
    resolved = resolve_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def read_jsonl(path: str | Path) -> list[dict]:
    resolved = resolve_path(path)
    if not resolved.exists():
        return []
    with resolved.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
