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

COMMAND = "agent_generate_mcp_config"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="imprvhub_mcp_rss_aggregator")
    args = parser.parse_args()

    configure_agent_logging(COMMAND)
    try:
        payload = generate_mcp_config_hint(args.server)
        print_agent_success(
            COMMAND,
            "MCP config hint generated.",
            output_paths(),
            {"server_id": payload["server_id"], "recommended": payload.get("recommended", False)},
        )
    except ValueError as exc:
        logging.exception("Invalid MCP server")
        print_agent_error(COMMAND, "MCP config generation failed.", "ConfigError", str(exc), exit_code=EXIT_CONFIG)
    except Exception as exc:  # noqa: BLE001
        logging.exception("MCP config generation failed")
        print_agent_error(COMMAND, "MCP config generation failed.", type(exc).__name__, str(exc))


if __name__ == "__main__":
    main()
