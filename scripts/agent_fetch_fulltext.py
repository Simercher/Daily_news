from __future__ import annotations

import argparse
import json
import logging

from news_feed_bootstrap.agent_io import configure_agent_logging, output_paths, print_agent_error, print_agent_success
from news_feed_bootstrap.fulltext_fetcher import run_fulltext_fetch
from news_feed_bootstrap.mcp_fetcher import mcp_healthcheck
from news_feed_bootstrap.pipeline import project_status


COMMAND = "agent_fetch_fulltext"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/news_item_labels.jsonl")
    parser.add_argument("--output", default="data/news_item_fulltext.jsonl")
    parser.add_argument("--healthcheck-url", default=None)
    args = parser.parse_args()

    configure_agent_logging(COMMAND)
    try:
        if args.healthcheck_url:
            print(json.dumps(mcp_healthcheck(args.healthcheck_url), ensure_ascii=False, indent=2))
            return
        rows = run_fulltext_fetch(input_path=args.input, output_path=args.output)
        status = project_status()
        stats = status["stats"] | {"fulltext_items": len(rows)}
        print_agent_success(COMMAND, "Article fulltext fetched.", output_paths(), stats, warnings=[])
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        logging.exception("Fulltext fetch failed")
        print_agent_error(COMMAND, "Article fulltext fetch failed.", type(exc).__name__, str(exc))


if __name__ == "__main__":
    main()
