from __future__ import annotations

import argparse
import logging

from news_feed_bootstrap.agent_io import (
    EXIT_CONFIG,
    configure_agent_logging,
    output_paths,
    print_agent_error,
    print_agent_success,
)
from news_feed_bootstrap.mcp_config_generator import generate_mcp_config_hint
from news_feed_bootstrap.pipeline import dedup_raw_items, path_is_stale, project_status, run_bootstrap, run_local_fetch

COMMAND = "agent_run_daily"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["local", "mcp", "auto"], default="local")
    parser.add_argument("--server", default="imprvhub_mcp_rss_aggregator")
    parser.add_argument("--since-hours", type=int, default=24)
    parser.add_argument("--force-bootstrap", action="store_true")
    parser.add_argument("--skip-bootstrap", action="store_true")
    args = parser.parse_args()

    configure_agent_logging(COMMAND)
    try:
        if args.force_bootstrap and args.skip_bootstrap:
            print_agent_error(
                COMMAND,
                "Invalid bootstrap options.",
                "ConfigError",
                "--force-bootstrap and --skip-bootstrap cannot be used together.",
                exit_code=EXIT_CONFIG,
            )
        warnings: list[str] = []
        if args.mode == "mcp":
            generate_mcp_config_hint(args.server)
            print_agent_error(
                COMMAND,
                "MCP fetch is not implemented in this MVP.",
                "ExternalServiceError",
                "Run agent_generate_mcp_config.py and call the RSS MCP tool externally, or use --mode local/auto.",
                warnings=["Fallback to local mode is available."],
                exit_code=3,
            )
        if args.mode == "auto":
            generate_mcp_config_hint(args.server)
            warnings.append(
                "MCP fetch is not implemented in this MVP; generated config hint and used local feedparser fallback."
            )

        should_bootstrap = args.force_bootstrap or (
            not args.skip_bootstrap
            and (path_is_stale("data/active_feeds.json") or path_is_stale("data/active_feeds.opml"))
        )
        if should_bootstrap:
            active = run_bootstrap(show_progress=False)
            if not active:
                warnings.append(
                    "Bootstrap produced zero active feeds. Check seed source network access or feed health."
                )
        elif args.skip_bootstrap:
            warnings.append("Bootstrap skipped by request; using existing active feed files.")

        raw = run_local_fetch(since_hours=args.since_hours)
        deduped = dedup_raw_items()
        status = project_status()
        stats = status["stats"] | {"raw_items": len(raw), "deduped_items": len(deduped)}
        print_agent_success(COMMAND, "Daily RSS pipeline completed.", output_paths(), stats, warnings)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        logging.exception("Daily run failed")
        print_agent_error(COMMAND, "Daily RSS pipeline failed.", type(exc).__name__, str(exc))


if __name__ == "__main__":
    main()
