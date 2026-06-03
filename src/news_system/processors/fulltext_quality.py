"""Full-text quality scoring for articles."""
from __future__ import annotations

import re
from datetime import datetime, timezone

BOILERPLATE_PATTERNS = [
    r"subscribe now", r"click here", r"read more", r"related articles",
    r"all rights reserved", r"terms of service", r"privacy policy",
    r"advertisement", r"newsletter", r"sign up", r"log in",
    r"\u00a9", r"cookie", r"by clicking", r"you agree",
]


def compute_fulltext_quality(content: str | None, status: str = "not_attempted") -> tuple[float, int]:
    """
    Compute fulltext_quality_score and store it.

    Returns (quality_score, content_length).
    """
    if status in ("blocked", "timeout", "error", "empty"):
        return (0.0, 0)
    if status == "paywalled":
        return (0.2, len(content or ""))
    if not content or status == "not_attempted":
        return (0.0, 0)

    length = len(content.strip())

    if length < 300:
        base = 0.2
    elif length < 500:
        base = 0.4
    elif length < 1500:
        base = 0.6
    else:
        base = 0.8

    # Boilerplate noise detection
    content_lower = content.lower()
    noise_hits = sum(1 for pat in BOILERPLATE_PATTERNS if re.search(pat, content_lower))
    noise_ratio = noise_hits / len(BOILERPLATE_PATTERNS)

    if noise_ratio >= 0.4:
        base = min(base, 0.7)

    return (round(min(1.0, base), 4), length)