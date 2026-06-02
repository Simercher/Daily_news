from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import read_yaml, write_yaml

_URL_FIELDS = ("feed_url", "homepage")


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _canonicalize_url(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    if text.startswith(("http://", "https://")):
        _, rest = text.split("://", 1)
        text = f"https://{rest}"
    return text


def _dedupe_key(row: dict[str, Any]) -> str:
    for field in _URL_FIELDS:
        value = _canonicalize_url(row.get(field))
        if value:
            return f"url:{value.casefold()}"
    raise ValueError("seed source row must define feed_url or homepage")


def _normalize_seed_source_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    if normalized.get("source_name") is None and normalized.get("name"):
        normalized["source_name"] = normalized["name"]
    if normalized.get("name") is None and normalized.get("source_name"):
        normalized["name"] = normalized["source_name"]
    if normalized.get("feed_url") is None and normalized.get("url"):
        normalized["feed_url"] = normalized["url"]
    if normalized.get("homepage") is None and normalized.get("htmlUrl"):
        normalized["homepage"] = normalized["htmlUrl"]
    for field in _URL_FIELDS:
        if normalized.get(field):
            normalized[field] = _normalize_text(normalized[field])
    normalized["enabled"] = bool(normalized.get("enabled", True))
    return normalized


def _expand_source_pack_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for row in rows:
        nested_sources = row.get("sources") or row.get("seed_sources") or []
        if nested_sources:
            parent = {key: value for key, value in row.items() if key not in {"sources", "seed_sources"}}
            for nested in nested_sources:
                expanded.append(_normalize_seed_source_row({**parent, **nested}))
            continue
        expanded.append(_normalize_seed_source_row(row))
    return expanded


def _merge_rows(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if value is None:
            continue
        if key == "topics":
            current = list(merged.get(key) or [])
            merged[key] = sorted({*current, *list(value)})
            continue
        if key == "enabled":
            # Explicit state should win: the current imported row decides whether
            # the merged record remains enabled or becomes disabled.
            merged[key] = bool(value)
            continue
        if key in _URL_FIELDS:
            existing_url = _canonicalize_url(merged.get(key))
            incoming_url = _canonicalize_url(value)
            if existing_url == incoming_url:
                merged[key] = existing_url or incoming_url or merged.get(key)
                continue
            if existing_url and incoming_url:
                merged[key] = incoming_url
                continue
        if key not in merged or merged[key] in (None, "", []):
            merged[key] = value
    return merged


def load_source_pack(path: str | Path) -> list[dict[str, Any]]:
    data = read_yaml(path, {}) or {}
    rows = data.get("seed_sources") or data.get("sources") or []
    return _expand_source_pack_rows(rows)


def merge_source_packs(
    pack_paths: list[str | Path],
    *,
    existing_config_path: str | Path = "configs/seed_sources.yaml",
    output_path: str | Path = "configs/seed_sources.yaml",
) -> list[dict[str, Any]]:
    existing_data = read_yaml(existing_config_path, {"seed_sources": []}) or {"seed_sources": []}
    merged_by_key: dict[str, dict[str, Any]] = {}

    for row in existing_data.get("seed_sources", []) or []:
        normalized = _normalize_seed_source_row(row)
        merged_by_key[_dedupe_key(normalized)] = normalized

    for pack_path in pack_paths:
        for row in load_source_pack(pack_path):
            key = _dedupe_key(row)
            if key in merged_by_key:
                merged_by_key[key] = _merge_rows(merged_by_key[key], row)
            else:
                merged_by_key[key] = row

    merged = list(merged_by_key.values())
    write_yaml(output_path, {"seed_sources": merged})
    return merged

