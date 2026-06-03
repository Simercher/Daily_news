"""Sitemap-based news collector.

Fetches a news sitemap index XML, discovers sub-sitemaps, and extracts
article URLs, titles, and publication dates using XML parsing (stdlib only).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import httpx

from news_system.schemas import Article

log = logging.getLogger(__name__)

_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"


class SitemapCollector:
    """Collect articles from an XML news sitemap.

    Handles:
      - Sitemap index (top-level) -> discovers sub-sitemaps
      - Sub-sitemap (urlset) -> extracts <loc>, <lastmod>, news:title, etc.
    """

    def __init__(self, sitemap_url: str, source_name: str | None = None, *, client: httpx.Client | None = None):
        self.sitemap_url = sitemap_url
        self.source_name = source_name
        self._client = client or httpx.Client()

    def fetch(self, **kwargs) -> list[Article]:
        """Fetch and parse the sitemap, returning Article objects."""

        lookback_hours = kwargs.get("lookback_hours", 24)
        cutoff = datetime.now(timezone.utc)

        # Step 1: fetch the sitemap index
        raw = self._fetch_xml(self.sitemap_url)
        if raw is None:
            return []

        root = ET.fromstring(raw)

        # Step 2: determine if this is a sitemap index or a urlset
        if root.tag == f"{{{_SITEMAP_NS}}}sitemapindex":
            # Discover sub-sitemaps and pick the most recent ones
            sub_urls = self._discover_sub_sitemaps(root, cutoff, lookback_hours)
        elif root.tag == f"{{{_SITEMAP_NS}}}urlset":
            sub_urls = [self.sitemap_url]
        else:
            log.warning("unexpected root tag %r in sitemap %s", root.tag, self.sitemap_url)
            return []

        # Step 3: parse each sub-sitemap for news articles
        seen: set[str] = set()
        articles: list[Article] = []
        for url in sub_urls:
            for a in self._parse_sub_sitemap(url, cutoff, lookback_hours):
                if a.url in seen:
                    continue
                seen.add(a.url)
                articles.append(a)

        return articles

    def _fetch_xml(self, url: str) -> str | None:
        try:
            resp = self._client.get(url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            log.warning("failed to fetch sitemap %s: %s", url, exc)
            return None

    def _discover_sub_sitemaps(self, root: ET.Element, now: datetime, lookback_hours: int) -> list[str]:
        """Return sub-sitemap URLs that have been updated recently enough."""
        candidates: list[tuple[str, datetime | None]] = []
        for sm in root.findall(f"{{{_SITEMAP_NS}}}sitemap"):
            loc_el = sm.find(f"{{{_SITEMAP_NS}}}loc")
            if loc_el is None or not loc_el.text:
                continue
            lastmod_el = sm.find(f"{{{_SITEMAP_NS}}}lastmod")
            lastmod: datetime | None = None
            if lastmod_el is not None and lastmod_el.text:
                try:
                    lastmod = datetime.fromisoformat(lastmod_el.text)
                    if lastmod.tzinfo is None:
                        lastmod = lastmod.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass
            # Only include sub-sitemaps updated recently enough
            if lastmod is not None and (now - lastmod).total_seconds() > lookback_hours * 3600 * 2:
                continue
            candidates.append((loc_el.text.strip(), lastmod))

        # Sort by most recently updated first
        candidates.sort(key=lambda t: t[1] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        # Return at most the 5 most recent sub-sitemaps
        return [url for url, _ in candidates[:5]]

    def _parse_sub_sitemap(self, url: str, now: datetime, lookback_hours: int) -> list[Article]:
        raw = self._fetch_xml(url)
        if raw is None:
            return []
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            log.warning("failed to parse sub-sitemap %s: %s", url, exc)
            return []

        articles: list[Article] = []
        for url_el in root.findall(f"{{{_SITEMAP_NS}}}url"):
            loc_el = url_el.find(f"{{{_SITEMAP_NS}}}loc")
            if loc_el is None or not loc_el.text:
                continue
            article_url = loc_el.text.strip()

            # Extract publication date
            pub_date = None
            news_el = url_el.find(f"{{{_NEWS_NS}}}news")
            if news_el is not None:
                pub_el = news_el.find(f"{{{_NEWS_NS}}}publication_date")
                if pub_el is not None and pub_el.text:
                    try:
                        pub_date = datetime.fromisoformat(pub_el.text)
                        if pub_date.tzinfo is None:
                            pub_date = pub_date.replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass

            # Fall back to lastmod if no news:publication_date
            if pub_date is None:
                lastmod_el = url_el.find(f"{{{_SITEMAP_NS}}}lastmod")
                if lastmod_el is not None and lastmod_el.text:
                    try:
                        pub_date = datetime.fromisoformat(lastmod_el.text)
                        if pub_date.tzinfo is None:
                            pub_date = pub_date.replace(tzinfo=timezone.utc)
                    except ValueError:
                        pass

            if pub_date is None:
                continue

            # Filter by lookback
            if (now - pub_date).total_seconds() > lookback_hours * 3600:
                continue

            # Extract news:title if available
            title = ""
            if news_el is not None:
                title_el = news_el.find(f"{{{_NEWS_NS}}}title")
                if title_el is not None and title_el.text:
                    title = title_el.text.strip()

            # Infer category from URL path
            category = self._infer_category(article_url)

            articles.append(Article(
                source_type="sitemap",
                source_name=self.source_name,
                title=title or "",
                url=article_url,
                published_at=pub_date,
                description="",
                category=category,
                raw={"sitemap_url": url, "fetched_via": "news_sitemap"},
            ))

        return articles

    @staticmethod
    def _infer_category(url: str) -> str | None:
        """Infer a broad category from the URL path."""
        from urllib.parse import urlparse
        path = urlparse(url).path.lower()
        for prefix, category in [
            ("/world/", "world"),
            ("/business/", "business"),
            ("/markets/", "markets"),
            ("/technology/", "technology"),
            ("/sports/", "sports"),
            ("/science/", "science"),
            ("/health/", "health"),
            ("/politics/", "politics"),
            ("/entertainment/", "entertainment"),
        ]:
            if path.startswith(prefix):
                return category
        return None