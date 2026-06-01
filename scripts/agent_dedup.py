from __future__ import annotations

import logging

from news_feed_bootstrap.agent_io import configure_agent_logging, output_paths, print_agent_error, print_agent_success
from news_feed_bootstrap.pipeline import dedup_raw_items, project_status

COMMAND = "agent_dedup"


def main() -> None:
    configure_agent_logging(COMMAND)
    try:
        items = dedup_raw_items()
        status = project_status()
        stats = status["stats"] | {"deduped_items": len(items)}
        print_agent_success(COMMAND, "RSS items deduplicated.", output_paths(), stats)
    except Exception as exc:  # noqa: BLE001
        logging.exception("Dedup failed")
        print_agent_error(COMMAND, "RSS dedup failed.", type(exc).__name__, str(exc))


if __name__ == "__main__":
    main()
