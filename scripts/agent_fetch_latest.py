from __future__ import annotations

import argparse
import logging

from news_feed_bootstrap.agent_io import (
    EXIT_EXTERNAL,
    configure_agent_logging,
    output_paths,
    print_agent_error,
    print_agent_success,
)
from news_feed_bootstrap.mcp_config_generator import generate_mcp_config_hint
from news_feed_bootstrap.pipeline import project_status, run_local_fetch

COMMAND = "agent_fetch_latest"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["local", "mcp", "auto"], default="local")
    parser.add_argument("--server", default="imprvhub_mcp_rss_aggregator")
    parser.add_argument("--since-hours", type=int, default=24)
    args = parser.parse_args()

    configure_agent_logging(COMMAND)
    try:
        warnings: list[str] = []
        generate_mcp_config_hint(args.server)
        if args.mode == "mcp":
            warnings.append("MCP is the primary fetch path; local feedparser is used only when MCP is unavailable.")
        if args.mode == "auto":
            warnings.append("MCP is preferred when available; local feedparser fallback remains enabled.")
        items = run_local_fetch(since_hours=args.since_hours)
        status = project_status()
        stats = status["stats"] | {"raw_items": len(items)}
        print_agent_success(COMMAND, "Latest RSS items fetched.", output_paths(), stats, warnings)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        logging.exception("Fetch failed")
        print_agent_error(COMMAND, "RSS fetch failed.", type(exc).__name__, str(exc))


if __name__ == "__main__":
    main()
