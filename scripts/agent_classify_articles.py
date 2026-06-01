from __future__ import annotations

import argparse
import logging

from news_feed_bootstrap.agent_io import configure_agent_logging, output_paths, print_agent_error, print_agent_success
from news_feed_bootstrap.classifier import run_article_classifier
from news_feed_bootstrap.pipeline import project_status

COMMAND = "agent_classify_articles"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/news_items_deduped.jsonl")
    parser.add_argument("--output", default="data/news_item_labels.jsonl")
    args = parser.parse_args()

    configure_agent_logging(COMMAND)
    try:
        labels = run_article_classifier(input_path=args.input, output_path=args.output)
        status = project_status()
        stats = status["stats"] | {"labeled_items": len(labels)}
        print_agent_success(COMMAND, "Article labels generated.", output_paths(), stats, warnings=[])
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        logging.exception("Classification failed")
        print_agent_error(COMMAND, "Article classification failed.", type(exc).__name__, str(exc))


if __name__ == "__main__":
    main()
