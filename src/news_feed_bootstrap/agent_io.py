from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import NoReturn

import orjson

from .config import DATA_DIR, ensure_data_dirs

EXIT_RECOVERABLE = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3


def configure_agent_logging(command: str) -> None:
    ensure_data_dirs()
    log_path = DATA_DIR / "logs" / f"{command}.log"
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    logging.captureWarnings(True)
    warnings.simplefilter("default")


def _print_json(payload: dict) -> None:
    print(orjson.dumps(payload, option=orjson.OPT_INDENT_2).decode("utf-8"))


def print_agent_success(
    command: str,
    message: str,
    outputs: dict,
    stats: dict,
    warnings: list[str] | None = None,
) -> None:
    _print_json(
        {
            "ok": True,
            "command": command,
            "message": message,
            "outputs": outputs,
            "stats": stats,
            "warnings": warnings or [],
        }
    )


def print_agent_error(
    command: str,
    message: str,
    error_type: str,
    detail: str,
    warnings: list[str] | None = None,
    exit_code: int = EXIT_RECOVERABLE,
) -> NoReturn:
    _print_json(
        {
            "ok": False,
            "command": command,
            "message": message,
            "error": {"type": error_type, "detail": detail},
            "outputs": {},
            "stats": {},
            "warnings": warnings or [],
        }
    )
    raise SystemExit(exit_code)


def output_paths() -> dict:
    return {
        "imported_feeds": "data/imported_feeds.json",
        "imported_feeds_opml": "data/imported_feeds.opml",
        "feed_health": "data/feed_health.jsonl",
        "active_feeds": "data/active_feeds.json",
        "active_feeds_opml": "data/active_feeds.opml",
        "inactive_feeds": "data/inactive_feeds.json",
        "news_items_raw": "data/news_items_raw.jsonl",
        "news_items_deduped": "data/news_items_deduped.jsonl",
        "mcp_config_hint": "data/logs/mcp_config_hint.json",
    }


def file_exists(path: str) -> bool:
    return Path(path).exists()
