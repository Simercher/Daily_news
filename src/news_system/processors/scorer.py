from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import log1p

SEVERITY_KEYWORDS = {"war", "earthquake", "attack", "crash", "explosion", "missile", "invasion", "conflict", "dead", "kill", "death", "fatal", "\u707e\u533a", "\u5730\u9707", "\u7206\u70b8", "\u88ad\u51fb"}
BREAKING_KEYWORDS = {"breaking", "urgent", "just now", "developing", "\u6700\u65b0", "\u7a81\u53d1", "\u5feb\u8baf", "\u7d27\u6025"}
HIGH_IMPACT_CATEGORIES = {"war_conflict", "disaster", "health"}
MEDIUM_IMPACT_CATEGORIES = {"politics", "economy", "crime", "technology", "climate"}
GEOPOLITICAL_ENTITIES = {"iran", "us", "china", "russia", "israel", "ukraine", "eu", "nato", "un"}

CATEGORY_IMPORTANCE = {
    "war_conflict": 1.00,
    "disaster": 0.95,
    "health": 0.85,
    "economy": 0.80,
    "politics": 0.80,
    "cybersecurity": 0.75,
    "climate": 0.65,
    "technology": 0.60,
    "crime": 0.55,
    "science": 0.45,
    "sports": 0.25,
    "entertainment": 0.20,
}


def _get_credibility(article):
    raw = getattr(article, "raw_payload", None) or getattr(article, "raw", None) or {}
    cfg = raw.get("source_config") if isinstance(raw, dict) else None
    if isinstance(cfg, dict):
        return cfg.get("credibility_score", 0.5)
    return 0.5


def _get_category_importance(article):
    cat = (getattr(article, "category", None) or "").lower()
    return CATEGORY_IMPORTANCE.get(cat, 0.3)


def _severity_keyword_score(articles):
    text = " ".join(getattr(a, "title", "") or "" for a in articles).lower()
    matches = sum(1 for kw in SEVERITY_KEYWORDS if kw in text)
    if matches >= 3:
        return 1.0
    if matches >= 2:
        return 0.8
    if matches >= 1:
        return 0.5
    return 0.0


def _breaking_keyword_score(articles):
    text = " ".join(getattr(a, "title", "") or "" for a in articles).lower()
    return 1.0 if any(kw in text for kw in BREAKING_KEYWORDS) else 0.0


def _geopolitical_score(articles):
    text = " ".join(getattr(a, "title", "") or "" for a in articles).lower()
    return min(1.0, sum(1 for e in GEOPOLITICAL_ENTITIES if e in text) / 3.0)


def _source_credibility_score(articles):
    """Compute source credibility score using unique source_domains only.

    Returns a dict with average_credibility_score, trusted_source_count_score, and final.
    """
    if not articles:
        return {"average_credibility_score": 0.5, "trusted_source_count_score": 0.0, "final": 0.5}
    # Unique source_domains only
    seen_domains = set()
    domain_credibilities = []
    for a in articles:
        domain = getattr(a, "source_domain", None) or getattr(a, "source_name", None)
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            cred = _get_credibility(a)
            domain_credibilities.append(cred)

    if not domain_credibilities:
        return {"average_credibility_score": 0.5, "trusted_source_count_score": 0.0, "final": 0.5}

    avg_credibility = sum(domain_credibilities) / len(domain_credibilities)

    # Count trusted sources (credibility >= 0.75)
    trusted_count = sum(1 for c in domain_credibilities if c >= 0.75)
    trusted_score = min(trusted_count / 4, 1.0)

    final = 0.6 * avg_credibility + 0.4 * trusted_score

    return {
        "average_credibility_score": round(avg_credibility, 4),
        "trusted_source_count_score": round(trusted_score, 4),
        "final": round(final, 4),
    }


def _impact_scope_score(articles):
    countries = {getattr(a, "country", None) for a in articles if getattr(a, "country", None)}
    return min(1.0, len(countries) / 5.0)


def score_event(event):
    articles = event.articles
    n = len(articles)
    if n == 0:
        event.score_breakdown = {}
        event.final_score = 0.0
        return event

    # --- Popular Score ---
    article_volume_score = min(1.0, n / 15.0)
    source_names = {getattr(a, "source_name", None) for a in articles}
    source_diversity_score = min(1.0, len(source_names) / 6.0)
    credible_sources = {getattr(a, "source_name", None) for a in articles if _get_credibility(a) >= 0.75}
    trusted_source_score = min(1.0, len(credible_sources) / 4.0)
    countries = {getattr(a, "country", None) for a in articles if getattr(a, "country", None)}
    country_diversity_score = min(1.0, len(countries) / 4.0)

    # Count articles from last 3 hours for velocity
    three_hours_ago = datetime.now(timezone.utc) - timedelta(hours=3)
    recent_3h = sum(
        1 for a in articles
        if (getattr(a, "published_at", None) or datetime.min.replace(tzinfo=timezone.utc)) >= three_hours_ago
    )
    recent_velocity_score = min(recent_3h / 10, 1.0)

    popular_score = (
        0.35 * article_volume_score
        + 0.30 * source_diversity_score
        + 0.20 * trusted_source_score
        + 0.10 * country_diversity_score
        + 0.05 * recent_velocity_score
    )

    # --- Importance Score ---
    category_importance_score = max(_get_category_importance(a) for a in articles) if articles else 0.3
    severity_kw_score = _severity_keyword_score(articles)
    geo_score = _geopolitical_score(articles)
    src_cred = _source_credibility_score(articles)
    src_cred_final = src_cred["final"]
    impact_score = _impact_scope_score(articles)

    importance_score = (
        0.35 * category_importance_score
        + 0.25 * severity_kw_score
        + 0.20 * geo_score
        + 0.10 * src_cred_final
        + 0.10 * impact_score
    )

    # --- Breaking Score ---
    # Count articles from last 60 minutes
    sixty_min_ago = datetime.now(timezone.utc) - timedelta(minutes=60)
    recent_60m = [
        a for a in articles
        if (getattr(a, "published_at", None) or datetime.min.replace(tzinfo=timezone.utc)) >= sixty_min_ago
    ]
    recent_growth_score = min(len(recent_60m) / 8, 1.0)

    # Unique source_domains in last 60m
    recent_sources_60m = set()
    for a in recent_60m:
        domain = getattr(a, "source_domain", None) or getattr(a, "source_name", None)
        if domain:
            recent_sources_60m.add(domain)
    recent_source_score = min(len(recent_sources_60m) / 4, 1.0)

    breaking_kw_score = _breaking_keyword_score(articles)
    breaking_score = (
        0.25 * recent_growth_score
        + 0.20 * recent_source_score
        + 0.20 * severity_kw_score
        + 0.15 * category_importance_score
        + 0.10 * src_cred_final
        + 0.10 * breaking_kw_score
    )

    # --- Final Score ---
    final_score = 0.45 * popular_score + 0.55 * importance_score

    # Store on event
    event.popular_score = round(popular_score, 4)
    event.importance_score = round(importance_score, 4)
    event.breaking_score = round(breaking_score, 4)
    event.final_score = round(final_score, 4)
    # Backward compat aliases for Event dataclass
    event.velocity_score = round(breaking_score, 4)
    event.source_diversity_score = round(popular_score, 4)
    event.severity_score = round(importance_score, 4)
    event.score_breakdown = {
        "popular_score": {
            "article_volume_score": round(article_volume_score, 4),
            "source_diversity_score": round(source_diversity_score, 4),
            "trusted_source_score": round(trusted_source_score, 4),
            "country_diversity_score": round(country_diversity_score, 4),
            "recent_velocity_score": round(recent_velocity_score, 4),
        },
        "importance_score": {
            "category_importance_score": round(category_importance_score, 4),
            "severity_keyword_score": round(severity_kw_score, 4),
            "geopolitical_score": round(geo_score, 4),
            "source_credibility_score": src_cred,
            "impact_scope_score": round(impact_score, 4),
        },
        "breaking_score": {
            "recent_growth_score": round(recent_growth_score, 4),
            "recent_source_score": round(recent_source_score, 4),
            "severity_keyword_score": round(severity_kw_score, 4),
            "category_importance_score": round(category_importance_score, 4),
            "source_credibility_score": round(src_cred_final, 4),
            "breaking_keyword_score": round(breaking_kw_score, 4),
        },
        "final_score": round(final_score, 4),
    }
    event.last_scored_at = datetime.now(timezone.utc)
    return event