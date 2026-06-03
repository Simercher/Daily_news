"""
Domain classification and summarization for news articles.
Maps articles into 4 domains: international, macro, stocks, tech_ai (plus other).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

# Category mapping from source config category → domain
CATEGORY_DOMAIN_MAP = {
    "world": "international",
    "politics": "international",
    "war_conflict": "international",
    "disaster": "international",
    "economy": "macro",
    "business": "macro",
    "finance": "macro",
    "markets": "stocks",
    "technology": "tech_ai",
    "science": "tech_ai",
}

# Domain-specific keywords (lowercase) for matching against title + description
DOMAIN_KEYWORDS = {
    "international": [
        "president", "minister", "election", "diplomat", "sanction", "treaty",
        "military", "war", "conflict", "ceasefire", "missile", "invasion",
        "foreign", "international", "united nations", "nato", "eu ", "china ",
        "russia", "ukraine", "taiwan", "israel", "iran", "gaza", "middle east",
        "africa", "europe", "asia", "border", "refugee", "ambassador",
        "sovereign", "diplomacy", "security council",
        # Chinese keywords for title matching
        "總統", "首相", "外交", "制裁", "軍事", "戰爭", "衝突", "選舉",
        "聯合國", "國際", "邊境", "難民", "大使", "主權",
    ],
    "macro": [
        "gdp", "inflation", "cpi", "central bank", "interest rate", "fed ",
        "federal reserve", "ecb", "monetary policy", "fiscal", "deficit",
        "treasury", "bond yield", "trade war", "tariff", "import", "export",
        "recession", "growth", "economic", "consumer price", "pmi",
        "manufacturing", "stimulus", "debt ceiling", "budget",
        # Chinese
        "通膨", "通脹", "利率", "央行", "聯準會", "GDP", "經濟成長",
        "關稅", "貿易戰", "財政", "貨幣政策", "衰退",
    ],
    "stocks": [
        "stock", "market", "nasdaq", "s&p 500", "dow jones", "ipo",
        "earnings", "quarterly", "dividend", "buyback", "etf",
        "bull market", "bear market", "volatility", "rally", "sell-off",
        "shares", "equity", "hedge fund", "institutional investor",
        "market cap", "valuation", "pe ratio", "blue chip",
        # Chinese
        "美股", "股市", "股票", "指數", "財報", "IPO", "上市",
        "散戶", "法人", "融資", "回購", "配息", "收益",
    ],
    "tech_ai": [
        "ai", "artificial intelligence", "machine learning", "deep learning",
        "llm", "large language model", "gpt", "openai", "anthropic",
        "neural network", "model", "algorithm", "chip", "semiconductor",
        "nvidia", "tsmc", "intel", "amd", "quantum", "robotics",
        "autonomous", "self-driving", "startup", "venture capital",
        "software", "cloud", "saas", "cyber", "data center",
        "blockchain", "crypto", "generative", "transformer",
        "5g", "6g", "satellite", "space", "battery", "ev ",
        # Chinese
        "AI", "人工智慧", "晶片", "半導體", "台積電", "輝達",
        "機器人", "自駕", "新創", "雲端", "軟體", "大模型",
    ],
}

# Source categories that get priority mapping for each domain
PRIORITY_CATEGORIES = {
    "international": ["world"],
    "macro": ["economy"],
    "stocks": ["markets"],
    "tech_ai": ["technology", "science"],
}


@dataclass
class ArticleSummary:
    title: str
    url: str
    source: str
    snippet: str
    published_at: str


@dataclass
class DomainGroup:
    domain: str
    display_name: str
    articles: List[ArticleSummary] = field(default_factory=list)


DOMAIN_DISPLAY_NAMES = {
    "international": "國際情勢",
    "macro": "金融總經",
    "stocks": "股票市場",
    "tech_ai": "科技AI",
    "other": "其他",
}

VALID_DOMAINS = {"international", "macro", "stocks", "tech_ai", "other"}


@dataclass
class ClassificationDecision:
    """Validated article-domain classification decision."""

    article_id: str
    index: int
    domain: str
    method: str
    rule_domain: str
    confidence: Optional[float] = None
    reason: Optional[str] = None


LLMClassifier = Callable[[List[Dict[str, Any]]], Any]


def _article_text(article) -> str:
    """Return normalized article text used for domain keyword scoring."""
    parts = [
        getattr(article, "title", None),
        getattr(article, "description", None),
        getattr(article, "content_snippet", None),
        getattr(article, "content", None),
        getattr(article, "body", None),
    ]
    return " ".join(str(part) for part in parts if part).casefold()


def _keyword_matches(text: str, keyword: str) -> bool:
    """Match ASCII keywords on token boundaries and CJK keywords by substring."""
    kw = keyword.casefold().strip()
    if not kw:
        return False
    if kw.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text) is not None
    return kw in text


def classify_article(article) -> str:
    """
    Classify a single article into: international, macro, stocks, tech_ai, or other.

    Priority:
    1. Keyword scoring on article title + description + content/body fields
    2. Source category as a tie-breaker or fallback when content is ambiguous
    3. Default: other
    """
    combined = _article_text(article)
    category = (getattr(article, "category", None) or "").casefold()
    category_domain = CATEGORY_DOMAIN_MAP.get(category)

    # Content-first score-based keyword matching.
    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if _keyword_matches(combined, kw))
        if score > 0:
            scores[domain] = score

    if scores:
        max_score = max(scores.values())
        top_domains = [domain for domain, score in scores.items() if score == max_score]
        if category_domain is not None and category_domain in top_domains:
            return category_domain
        return top_domains[0]

    if category_domain:
        return category_domain

    return "other"



def _get_article_id(article: Any, index: int) -> str:
    """Return a stable article id when present, otherwise the stable batch index."""
    for attr in ("id", "article_id", "uuid", "url"):
        value = getattr(article, attr, None)
        if value:
            return str(value)
    return str(index)


def _truncate_text(value: Any, limit: int = 1200) -> str:
    if value is None:
        return ""
    return str(value)[:limit]


def _source_name(article: Any) -> str:
    return (
        getattr(article, "source_name", None)
        or getattr(article, "source_domain", None)
        or getattr(article, "source", None)
        or ""
    )


def _build_llm_payload_item(article: Any, index: int, rule_domain: str) -> Dict[str, Any]:
    """Build one compact, serializable article row for LLM classification."""
    content = (
        getattr(article, "content_snippet", None)
        or getattr(article, "content", None)
        or getattr(article, "body", None)
        or ""
    )
    return {
        "id": _get_article_id(article, index),
        "index": index,
        "title": getattr(article, "title", "") or "",
        "source": _source_name(article),
        "category": getattr(article, "category", None) or "",
        "description": _truncate_text(getattr(article, "description", None), 700),
        "content_snippet": _truncate_text(content, 1200),
        "rule_domain": rule_domain,
    }


def _parse_llm_response(response: Any) -> List[Dict[str, Any]]:
    """Parse accepted LLM response shapes into list[dict]."""
    if isinstance(response, str):
        response = json.loads(response)
    if isinstance(response, dict):
        for key in ("classifications", "results", "items"):
            if isinstance(response.get(key), list):
                response = response[key]
                break
    if not isinstance(response, list):
        raise ValueError("LLM classifier response must be a list or JSON list")
    return [item for item in response if isinstance(item, dict)]


def _fallback_decision(article: Any, index: int, rule_domain: str, reason: Optional[str] = None) -> ClassificationDecision:
    return ClassificationDecision(
        article_id=_get_article_id(article, index),
        index=index,
        domain=rule_domain,
        method="rule",
        rule_domain=rule_domain,
        reason=reason,
    )


def classify_articles_with_decisions(
    articles,
    llm_classifier: Optional[LLMClassifier] = None,
    batch_size: int = 50,
) -> Tuple[Dict[str, list], Dict[str, ClassificationDecision]]:
    """Group articles by domain and return per-article classification metadata.

    The injected ``llm_classifier`` receives a list of article payload dicts and
    should return rows containing ``id`` or ``index`` plus ``domain``. Only
    domains in ``VALID_DOMAINS`` are accepted. Missing rows, invalid domains,
    invalid JSON/shapes, or classifier exceptions deterministically fall back to
    the article's rule-based domain.
    """
    articles = list(articles)
    groups = {d: [] for d in ["international", "macro", "stocks", "tech_ai", "other"]}
    decisions: Dict[str, ClassificationDecision] = {}
    rule_domains = [classify_article(article) for article in articles]

    if llm_classifier is None:
        for index, (article, rule_domain) in enumerate(zip(articles, rule_domains)):
            decision = _fallback_decision(article, index, rule_domain)
            decisions[decision.article_id] = decision
            groups[decision.domain].append(article)
        return groups, decisions

    batch_size = max(1, int(batch_size or 50))
    for start in range(0, len(articles), batch_size):
        batch_articles = articles[start:start + batch_size]
        payload = [
            _build_llm_payload_item(article, start + offset, rule_domains[start + offset])
            for offset, article in enumerate(batch_articles)
        ]

        try:
            rows = _parse_llm_response(llm_classifier(payload))
            by_index = {row.get("index"): row for row in rows if row.get("index") is not None}
            by_id = {str(row.get("id")): row for row in rows if row.get("id") is not None}
        except Exception as exc:
            for offset, article in enumerate(batch_articles):
                index = start + offset
                decision = _fallback_decision(article, index, rule_domains[index], f"llm_exception: {exc}")
                decisions[decision.article_id] = decision
                groups[decision.domain].append(article)
            continue

        for offset, article in enumerate(batch_articles):
            index = start + offset
            article_id = _get_article_id(article, index)
            row = by_index.get(index) or by_id.get(article_id)
            if row is None:
                decision = _fallback_decision(article, index, rule_domains[index], "missing_llm_result")
            else:
                domain = row.get("domain")
                if domain not in VALID_DOMAINS:
                    decision = _fallback_decision(article, index, rule_domains[index], f"invalid_llm_domain: {domain!r}")
                else:
                    decision = ClassificationDecision(
                        article_id=article_id,
                        index=index,
                        domain=domain,
                        method="llm",
                        rule_domain=rule_domains[index],
                        confidence=row.get("confidence"),
                        reason=row.get("reason"),
                    )
            decisions[decision.article_id] = decision
            groups[decision.domain].append(article)

    return groups, decisions


def classify_articles_with_llm(articles, llm_classifier: Optional[LLMClassifier] = None, batch_size: int = 50) -> Dict[str, list]:
    """LLM-capable grouping API; returns only domain groups for caller compatibility."""
    groups, _ = classify_articles_with_decisions(articles, llm_classifier=llm_classifier, batch_size=batch_size)
    return groups


def classify_articles(articles) -> Dict[str, list]:
    """Group articles by domain. Returns dict of domain → [articles]."""
    return classify_articles_with_llm(articles, llm_classifier=None)


def _is_scrapling_fallback_date(article) -> bool:
    raw = getattr(article, "raw_payload", None) or getattr(article, "raw", None) or {}
    return (
        getattr(article, "source_type", None) == "scrapling"
        and raw.get("date_parse_status") != "parsed"
        and raw.get("date_source") in {"fallback_sentinel", "collected_at", "fallback_collected_at"}
    )


def build_domain_summaries(classified: Dict[str, list], max_articles=25) -> Dict[str, dict]:
    """
    Build structured summaries per domain.

    Returns:
    {
        "international": {
            "display_name": "國際情勢",
            "domain": "international",
            "count": 5,
            "articles": [
                {
                    "title": "...",
                    "url": "...",
                    "source": "BBC",
                    "snippet": "...",
                },
                ...
            ]
        },
        ...
    }
    """
    result = {}
    for domain, articles in classified.items():
        if not articles:
            result[domain] = {
                "display_name": DOMAIN_DISPLAY_NAMES.get(domain, domain),
                "domain": domain,
                "count": 0,
                "articles": [],
            }
            continue

        summaries = []
        recency_articles = [a for a in articles if not _is_scrapling_fallback_date(a)]
        sortable_articles = recency_articles or articles
        sorted_articles = sorted(
            sortable_articles,
            key=lambda a: getattr(a, "published_at", datetime.now(timezone.utc)) or datetime.now(timezone.utc),
            reverse=True,
        )

        for article in sorted_articles[:max_articles]:
            snippet = (getattr(article, "description", None) or getattr(article, "content_snippet", None) or "")[:500]
            summaries.append(ArticleSummary(
                title=getattr(article, "title", "") or "",
                url=getattr(article, "url", "") or "",
                source=getattr(article, "source_name", None) or getattr(article, "source_domain", None) or "unknown",
                snippet=snippet,
                published_at=str(getattr(article, "published_at", "")),
            ))

        result[domain] = {
            "display_name": DOMAIN_DISPLAY_NAMES.get(domain, domain),
            "domain": domain,
            "count": len(summaries),
            "articles": [asdict(s) for s in summaries],
        }

    return result


def format_for_discord(domain_data: Dict[str, dict]) -> Dict[str, str]:
    """
    Format each domain group into a Discord-friendly message.
    Returns dict of domain → formatted message string.
    """
    messages = {}
    for domain, data in domain_data.items():
        if data["count"] == 0:
            continue
        lines = [f"# {data['display_name']} — {data['count']} 則"]
        for i, a in enumerate(data["articles"], 1):
            snippet = a["snippet"][:200] if a["snippet"] else ""
            lines.append(f"\n**{i}. [{a['title']}]({a['url']})**")
            lines.append(f"   ⚡ {a['source']}")
            if snippet:
                lines.append(f"   > {snippet}")
        messages[domain] = "\n".join(lines)
    return messages
