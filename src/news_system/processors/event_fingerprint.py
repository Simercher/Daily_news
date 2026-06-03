"""Event fingerprint generation to identify the same event across sources."""
from __future__ import annotations

from datetime import datetime, timezone


def date_bucket(dt: datetime | None) -> str:
    """Bucket by date for fingerprint comparison."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%d")


def extract_top_entities(entities: list | set, max_n: int = 3) -> list[str]:
    """Get top entities as sorted list."""
    ents = list(entities) if isinstance(entities, (list, set)) else list(entities or [])
    return [str(e).lower().strip() for e in ents[:max_n] if e]


def extract_top_keywords(keywords: list | set, max_n: int = 5) -> list[str]:
    """Get top keywords as sorted list."""
    kw = list(keywords) if isinstance(keywords, (list, set)) else list(keywords or [])
    return [str(k).lower().strip() for k in kw[:max_n] if k]


def generate_fingerprint(*, category: str | None, dt: datetime | None,
                          collected_at: datetime | None = None,
                          entities: list | set | None = None,
                          keywords: list | set | None = None,
                          source_country: str | None = None,
                          normalized_title: str | None = None) -> str:
    """
    Generate event fingerprint.
    Format: {category}|{date_bucket}|{top_entities}|{top_keywords}

    Falls back to collected_at if dt is None.
    Falls back to source_country if no entities provided.
    Falls back to title tokens if no keywords provided.
    """
    cat = (category or "unknown").lower().strip()

    # Use published_at if available, fallback to collected_at
    if dt is None and collected_at is not None:
        dt = collected_at
    bucket = date_bucket(dt)

    # Entities: use provided, or fallback to source_country
    ent_list = list(entities) if isinstance(entities, (list, set)) else list(entities or [])
    if not ent_list and source_country:
        ent_list = [source_country]

    # Keywords: use provided, or fallback to title tokens
    kw_list = list(keywords) if isinstance(keywords, (list, set)) else list(keywords or [])
    if not kw_list and normalized_title:
        import re
        tokens = re.findall(r'\w+', normalized_title.lower())
        kw_list = tokens[:5]

    # Sort for stability
    ents = ",".join(sorted(extract_top_entities(ent_list, 3)))
    kws = ",".join(sorted(extract_top_keywords(kw_list, 5)))

    return f"{cat}|{bucket}|{ents}|{kws}"


def fingerprint_overlap(fp1: str, fp2: str) -> float:
    """
    Compute overlap ratio between two fingerprints.
    Checks category match, date bucket match, entity overlap, keyword overlap.
    Returns 0.0-1.0
    """
    parts1 = fp1.split("|")
    parts2 = fp2.split("|")
    if len(parts1) < 4 or len(parts2) < 4:
        return 0.0

    # Category must match
    if parts1[0] != parts2[0]:
        return 0.0

    # Date bucket must match
    if parts1[1] != parts2[1]:
        return 0.0

    # Entity overlap
    e1 = set(e.strip() for e in parts1[2].split(",") if e.strip())
    e2 = set(e.strip() for e in parts2[2].split(",") if e.strip())
    entity_overlap = len(e1 & e2) / max(1, len(e1 | e2)) if e1 or e2 else 0.0

    # Keyword overlap
    k1 = set(k.strip() for k in parts1[3].split(",") if k.strip())
    k2 = set(k.strip() for k in parts2[3].split(",") if k.strip())
    keyword_overlap = len(k1 & k2) / max(1, len(k1 | k2)) if k1 or k2 else 0.0

    if entity_overlap >= 0.5 and keyword_overlap >= 0.4:
        return 1.0  # same event
    return 0.0