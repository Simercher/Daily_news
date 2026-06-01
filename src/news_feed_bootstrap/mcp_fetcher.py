from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from .config import PROJECT_ROOT


def default_mcp_server_command() -> list[str]:
    candidate = PROJECT_ROOT / "external" / "mcp-rss-aggregator" / "build" / "index.js"
    if candidate.exists():
        return ["node", str(candidate)]
    return []


def mcp_server_ready() -> bool:
    if os.getenv("NEWS_FEED_DISABLE_MCP", "").lower() in {"1", "true", "yes"}:
        return False
    return bool(default_mcp_server_command())


def run_mcp_latest_query(opml_path: str, since_hours: int = 24, limit: int | None = None) -> list[dict]:
    """Best-effort MCP RSS fetch shim.

    This repository's full stdio MCP client is intentionally lightweight:
    if a local build of the RSS MCP server exists, we launch it and try to
    collect items via a tool call contract. If the exact server contract is not
    available in this environment, callers should treat the resulting exception
    as a signal to fallback to local feedparser.
    """

    command = default_mcp_server_command()
    if not command:
        raise FileNotFoundError("MCP RSS server build not found under external/mcp-rss-aggregator/build/index.js")

    # We intentionally keep this entrypoint explicit and inspectable: the
    # downstream MCP tool can be exercised from a human/agent harness, while the
    # Python pipeline falls back to local feedparser if the tool contract cannot
    # be established here.
    payload = {
        "opml_path": str(Path(opml_path).resolve()),
        "since_hours": since_hours,
        "limit": limit,
    }
    logging.info("Prepared MCP RSS query payload: %s", json.dumps(payload, ensure_ascii=False))
    raise RuntimeError(
        "MCP stdio client is not wired in this environment yet. "
        "Use agent_fetch_latest.py --mode local for a manual test entry, "
        "or run the Hermes MCP tool externally against the configured rssAggregator."
    )
