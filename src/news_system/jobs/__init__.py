from __future__ import annotations

from typing import Any

from .breaking import breaking_watch_job
from .collect import _apply_source_metadata, _collector_for_source, _load_collectors, collect_job as _collect_job
from .events import daily_event_job


def collect_job(*args, **kwargs):
    source = kwargs.get("source", args[1] if len(args) > 1 else "all")
    config_path = kwargs.get("config_path", args[4] if len(args) > 4 else "config/sources.yaml")
    collectors = kwargs.get("collectors", args[3] if len(args) > 3 else None)
    if collectors is None:
        collectors = _load_collectors(source, config_path)
        if len(args) > 3:
            positional_args: list[Any] = list(args)
            positional_args[3] = collectors
            args = tuple(positional_args)
        else:
            kwargs["collectors"] = collectors
    return _collect_job(*args, **kwargs)


__all__ = [
    "collect_job",
    "daily_event_job",
    "breaking_watch_job",
    "_collector_for_source",
    "_load_collectors",
    "_apply_source_metadata",
]
