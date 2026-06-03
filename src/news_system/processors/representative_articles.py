"""Select representative articles for an event."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from news_system.processors.scorer import _get_credibility


def select_representative(articles: list, max_articles: int = 5) -> tuple[int | None, list[dict]]:
    """
    Select representative article(s) for an event.
    
    Returns (best_article_id, representative_articles_list).
    
    Selection rules:
    1. Filter out duplicates
    2. Prefer high credibility sources
    3. Prefer high fulltext quality
    4. Prefer earlier publication
    5. Title length between 40-140 chars
    6. Max 1 article per source_domain
    7. Max max_articles total
    """
    candidates = []
    seen_domains = set()

    # Sort: credibility desc, fulltext_quality desc, published_at asc
    scored = []
    for a in articles:
        if getattr(a, "is_duplicate", False):
            continue
        cred = _get_credibility(a)
        ft_score = getattr(a, "fulltext_quality_score", 0.0) or 0.0
        title_len = len(getattr(a, "title", "") or "")
        pub_at = getattr(a, "published_at", None)
        domain = getattr(a, "source_domain", None) or getattr(a, "source_name", None)

        scored.append({
            "article": a,
            "credibility": cred,
            "fulltext_quality": ft_score,
            "title_length": title_len,
            "published_at": pub_at,
            "domain": domain,
        })

    # Sort by credibility desc, fulltext_quality desc, published_at asc
    scored.sort(key=lambda x: (-x["credibility"], -x["fulltext_quality"], x["published_at"] or datetime.min.replace(tzinfo=timezone.utc)))

    results = []
    best_id = None

    for s in scored:
        if len(results) >= max_articles:
            break
        domain = s["domain"]
        
        # Title length filter (check BEFORE domain dedup)
        tl = s["title_length"]
        if tl < 40 or tl > 140:
            continue
            
        if domain in seen_domains:
            continue
        seen_domains.add(domain)

        results.append({
            "id": getattr(s["article"], "id", None),
            "title": getattr(s["article"], "title", ""),
            "url": getattr(s["article"], "url", ""),
            "source_name": getattr(s["article"], "source_name", ""),
            "source_domain": s["domain"],
            "credibility_score": s["credibility"],
            "fulltext_quality_score": s["fulltext_quality"],
            "published_at": s["published_at"].isoformat() if s["published_at"] else None,
        })

    best_id = results[0]["id"] if results else None
    return (best_id, results)