from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from news_system.schemas import Article
from news_system.collectors import BaseCollector


class NewsDataCollector(BaseCollector):
    """Collector for NewsData.io API (free tier: 200 req/day, 7-day lookback)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://newsdata.io/api/1",
        *,
        api_key_env: str = "NEWSDATA_API_KEY",
        client: httpx.Client | None = None,
        ):
        self.api_key = api_key or os.getenv(api_key_env)
        self.api_key_env = api_key_env
        self.base_url = (base_url or "https://newsdata.io/api/1").rstrip("/")
        self.client = client or httpx

    def fetch(self, **params) -> list[Article]:
        from news_system.processors.normalizer import to_utc

        if not self.api_key:
            raise ValueError(
                f"NewsData.io API key is required "
                f"(set api_key or {self.api_key_env} env var)"
            )

        # Resolve source-level params (from sources.yaml)
        if "q" in params and params["q"] is not None:
            pass  # use explicit query override
        elif "query" in params and params["query"] is not None:
            params["q"] = params.pop("query")

        # Strip pipeline-internal keys that aren't API parameters
        api_params = {
            "apikey": self.api_key,
        }
        for key in ("q", "country", "category", "language", "size", "page"):
            val = params.get(key)
            if val is not None:
                api_params[key] = val

        out: list[Article] = []
        next_page: str | None = None

        # Try first page; follow pagination on free tier if needed
        for attempt in range(2):  # max 2 pages (free tier limit ~50 per page)
            if next_page:
                api_params["page"] = next_page

            r = self.client.get(
                f"{self.base_url}/news", params=api_params, timeout=20
            )
            r.raise_for_status()
            body = r.json()

            if body.get("status") != "success":
                raise RuntimeError(
                    f"NewsData.io API error: {body.get('status', 'unknown')} — "
                    f"{body.get('results', body)}"
                )

            for a in (body.get("results") or []):
                pub = a.get("pubDate") or datetime.now(timezone.utc).isoformat()
                creators = a.get("creator") or []
                categories = a.get("category") or []
                countries = a.get("country") or []
                source_id = a.get("source_id")

                out.append(Article(
                    source_type="newsdata",
                    title=a.get("title") or "",
                    url=a.get("link") or "",
                    published_at=to_utc(pub),
                    source_id=str(source_id) if source_id else None,
                    source_name=a.get("source_name") or source_id,
                    author=creators[0] if isinstance(creators, list) and creators else None,
                    description=a.get("description"),
                    content=a.get("content"),
                    image_url=a.get("image_url"),
                    country=countries[0][:16] if isinstance(countries, list) and countries else None,
                    category=categories[0] if isinstance(categories, list) and categories else None,
                    language=a.get("language"),
                    raw=dict(a),
                ))

            next_page = body.get("nextPage")
            if not next_page:
                break

        return out
