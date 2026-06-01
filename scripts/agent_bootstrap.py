from __future__ import annotations

import logging

from news_feed_bootstrap.agent_io import configure_agent_logging, output_paths, print_agent_error, print_agent_success
from news_feed_bootstrap.pipeline import bootstrap_candidates, build_active_feeds, project_status

COMMAND = "agent_bootstrap"


def main() -> None:
    configure_agent_logging(COMMAND)
    try:
        imported = bootstrap_candidates()
        active = build_active_feeds(show_progress=False)
        status = project_status()
        stats = status["stats"] | {"imported_feeds": len(imported), "active_feeds": len(active)}
        warnings = []
        if not imported:
            warnings.append("No feeds were imported. Check seed source network access or raw URLs.")
        print_agent_success(COMMAND, "RSS feed bootstrap completed.", output_paths(), stats, warnings)
    except Exception as exc:  # noqa: BLE001 - agent boundary converts all failures to JSON.
        logging.exception("Bootstrap failed")
        print_agent_error(COMMAND, "RSS feed bootstrap failed.", type(exc).__name__, str(exc))


if __name__ == "__main__":
    main()
