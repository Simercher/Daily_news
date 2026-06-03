from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

VALID_SOURCE_TYPES = {"rss", "newsapi", "gdelt", "sitemap", "api", "newsdata", "scrapling"}
DEFAULT_PATH = "config/sources.yaml"


class SourceConfigError(ValueError):
    """Raised when source configuration is invalid."""


@dataclass(slots=True)
class SourceConfig:
    name: str
    source_type: str
    enabled: bool = True
    url: str | None = None
    query: str | None = None
    country: str | None = None
    category: str | None = None
    trusted: bool = False
    priority: int = 100
    language: str | None = None
    domain: str | None = None
    base_url: str | None = None
    credibility_score: float = 0.5
    region: str | None = None
    ownership_type: str | None = None
    source_notes: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "on"}: return True
        if v in {"0", "false", "no", "n", "off"}: return False
    raise SourceConfigError(f"invalid boolean value: {value!r}")


def _norm_text(value: Any, *, lower: bool = True) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    return value.lower() if lower else value


def _norm_priority(value: Any) -> int:
    if value is None:
        return 100
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SourceConfigError(f"invalid priority: {value!r}") from exc


def _domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host or None


def _normalize_source(raw: dict[str, Any], index: int) -> SourceConfig:
    if not isinstance(raw, dict):
        raise SourceConfigError(f"source #{index} must be an object")
    name = _norm_text(raw.get("name"), lower=False)
    if not name:
        raise SourceConfigError(f"source #{index} missing name")
    source_type = _norm_text(raw.get("source_type", raw.get("type")))
    if not source_type:
        raise SourceConfigError(f"source {name!r} missing source_type")
    if source_type not in VALID_SOURCE_TYPES:
        raise SourceConfigError(f"source {name!r} has invalid source_type {source_type!r}")

    url = _norm_text(raw.get("url"), lower=False)
    query = _norm_text(raw.get("query"), lower=False)
    base_url = _norm_text(raw.get("base_url"), lower=False)
    if source_type == "rss" and not url:
        raise SourceConfigError(f"rss source {name!r} missing url")
    if source_type in {"newsapi", "gdelt"} and not any([query, url, base_url]):
        raise SourceConfigError(f"{source_type} source {name!r} needs query, url, or base_url")

    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise SourceConfigError(f"source {name!r} params must be an object")

    domain = _norm_text(raw.get("domain")) or _domain_from_url(url) or _domain_from_url(base_url)
    return SourceConfig(
        name=name,
        source_type=source_type,
        enabled=_as_bool(raw.get("enabled"), default=True),
        url=url,
        query=query,
        country=_norm_text(raw.get("country")),
        category=_norm_text(raw.get("category")),
        trusted=_as_bool(raw.get("trusted"), default=False),
        priority=_norm_priority(raw.get("priority")),
        language=_norm_text(raw.get("language")),
        domain=domain,
        base_url=base_url,
        credibility_score=float(raw.get("credibility_score") or 0.5),
        region=_norm_text(raw.get("region")),
        ownership_type=_norm_text(raw.get("ownership_type")),
        source_notes=_norm_text(raw.get("source_notes"), lower=False),
        params=dict(params),
    )


def _extract_sources(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("sources"), list):
        return data["sources"]
    # Backward-compatible read of old grouped schema.
    if isinstance(data, dict):
        out: list[dict[str, Any]] = []
        for typ in VALID_SOURCE_TYPES:
            value = data.get(typ)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        out.append({"source_type": typ, **item})
            elif isinstance(value, dict):
                out.append({"name": typ, "source_type": typ, **value, "enabled": False})
        if out:
            return out
    raise SourceConfigError("sources config must contain a top-level 'sources' list")


def validate_sources(sources: list[SourceConfig] | list[dict[str, Any]]) -> list[SourceConfig]:
    normalized: list[SourceConfig] = []
    seen: set[str] = set()
    for idx, item in enumerate(sources, start=1):
        src = item if isinstance(item, SourceConfig) else _normalize_source(item, idx)
        key = src.name.lower()
        if key in seen:
            raise SourceConfigError(f"duplicate source name: {src.name!r}")
        seen.add(key)
        normalized.append(src)
    return normalized


def load_sources(path: str | Path = DEFAULT_PATH) -> list[SourceConfig]:
    p = Path(path)
    try:
        data = yaml.safe_load(p.read_text())
    except FileNotFoundError as exc:
        raise SourceConfigError(f"sources config not found: {p}") from exc
    except yaml.YAMLError as exc:
        raise SourceConfigError(f"invalid YAML in {p}: {exc}") from exc
    return validate_sources(_extract_sources(data))
