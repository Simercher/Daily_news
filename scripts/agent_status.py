from __future__ import annotations

import logging

from news_feed_bootstrap.agent_io import configure_agent_logging, print_agent_error, print_agent_success
from news_feed_bootstrap.pipeline import project_status

COMMAND = "agent_status"


def main() -> None:
    configure_agent_logging(COMMAND)
    try:
        status = project_status()
        print_agent_success(COMMAND, "Project status collected.", status["files"], status["stats"], warnings=[])
    except Exception as exc:  # noqa: BLE001
        logging.exception("Status failed")
        print_agent_error(COMMAND, "Project status failed.", type(exc).__name__, str(exc))


if __name__ == "__main__":
    main()
