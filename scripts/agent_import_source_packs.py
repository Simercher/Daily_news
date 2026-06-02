from __future__ import annotations

import argparse
import json
from pathlib import Path

from news_feed_bootstrap.source_pack_importer import merge_source_packs

COMMAND = "agent_import_source_packs"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack_paths", nargs="+")
    parser.add_argument("--output-path", default="configs/seed_sources.yaml")
    args = parser.parse_args()

    merged = merge_source_packs(args.pack_paths, output_path=args.output_path)
    payload = {
        "command": COMMAND,
        "status": "ok",
        "packs": [str(Path(path)) for path in args.pack_paths],
        "output_path": args.output_path,
        "merged_sources": len(merged),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
