from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from patchright.sync_api import sync_playwright

from news_system.collectors import BaseCollector
from news_system.schemas import Article

logger = logging.getLogger(__name__)

CHROME_PATH = "/opt/data/.cache/patchright/chromium-1223/chrome-linux/chrome"

# Common URL patterns that indicate a news article (relative paths or pattern substrings)
ARTICLE_PATH_PATTERNS = [
    re.compile(r"/article/", re.I),
    re.compile(r"/news/", re.I),
    re.compile(r"/story/", re.I),
    re.compile(r"/[0-9]{4}/[0-9]{2}/[0-9]{2}/", re.I),  # /YYYY/MM/DD/
    re.compile(r"/[a-z]{2}/[0-9]{6,}", re.I),             # /en/123456 (AP-style)
    re.compile(r"-story-", re.I),
    re.compile(r"/[a-z-]+/[a-z-]+/[a-z-]+-[a-z-]+-[a-z-]+-[a-z-]+", re.I),  # /section/subsection/long-hyphenated-slug (Nikkei articles)
    re.compile(r"/[a-z-]+/[0-9]{8,}", re.I),                   # /category/YYYYMMDDNN (CNA/Focus Taiwan)
]


class ScraplingPlaywrightCollector(BaseCollector):
    """Scrape article headlines and summaries from websites using Playwright
    (via patchright).  Useful for news sites that serve JS-rendered content
    and do not expose a public RSS feed."""

    def __init__(
        self,
        base_url: str,
        source_name: str | None = None,
        *,
        link_selector: str | None = None,
        content_selector: str | None = None,
        max_articles: int = 10,
        page_timeout: int = 30000,
    ):
        self.base_url = base_url.rstrip("/")
        self.source_name = source_name
        self.link_selector = link_selector  # e.g. "a[href*='/article/']"
        self.content_selector = content_selector  # e.g. "article p"
        self.max_articles = max_articles
        self.page_timeout = page_timeout

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _looks_like_article(href: str) -> bool:
        """Return True if *href* matches any of the known article patterns."""
        for pat in ARTICLE_PATH_PATTERNS:
            if pat.search(href):
                return True
        return False

    def _absolute_url(self, href: str) -> str:
        """Resolve a potentially relative *href* against *base_url*."""
        if href.startswith("http://") or href.startswith("https://"):
            return href
        return urljoin(self.base_url, href)

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_title(page) -> str:
        """Pull the document title, falling back to h1."""
        title = page.title()
        if title:
            return title.strip()
        h1 = page.query_selector("h1")
        if h1:
            return h1.inner_text().strip()
        return ""

    @staticmethod
    def _extract_summary(page) -> str | None:
        """Return the first meaningful paragraph from the page body."""
        # Try common selectors for article / lede text
        for sel in ("article p", ".article-body p", ".story-body p", "p", "[data-qa='article-text'] p"):
            paragraphs = page.query_selector_all(sel)
            if not paragraphs:
                continue
            for p in paragraphs:
                text = p.inner_text().strip()
                # Skip very short / clearly non-summary snippets
                if len(text) > 60:
                    return text
        return None

    # ------------------------------------------------------------------
    # Article-link discovery
    # ------------------------------------------------------------------
    def _find_article_links(self, page) -> list[str]:
        """Collect up to *max_articles* absolute article URLs from the page."""
        links: list[str] = []
        seen: set[str] = set()

        anchors = page.query_selector_all("a[href]")
        for a in anchors:
            href = a.get_attribute("href")
            if not href:
                continue
            href = href.strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            # Resolve to absolute
            abs_url = self._absolute_url(href)

            # Skip anchors that are clearly not articles
            parsed = urlparse(abs_url)
            path = parsed.path.rstrip("/")
            if not path or path in ("/", ""):
                continue

            # De-duplicate
            if abs_url in seen:
                continue
            seen.add(abs_url)

            if self._looks_like_article(abs_url):
                links.append(abs_url)
                if len(links) >= self.max_articles:
                    break

        return links

    # ------------------------------------------------------------------
    # Main fetch
    # ------------------------------------------------------------------
    def fetch(self, lookback_hours: int | None = None, **params) -> list[Article]:
        """Launch headless Chromium, visit *base_url*, discover article
        links, visit each article page, extract title + summary, and return
        ``list[Article]``."""
        _ = lookback_hours, params  # unused but accepted for pipeline compatibility
        articles: list[Article] = []
        browser = None

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    executable_path=CHROME_PATH,
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox"],
                )
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                    ),
                )
                homepage = context.new_page()

                # ── 1. Load homepage and collect article links ──────────
                logger.info("Navigating to %s …", self.base_url)
                try:
                    homepage.goto(self.base_url, timeout=self.page_timeout, wait_until="domcontentloaded")
                except Exception as exc:
                    logger.warning("Timeout / error loading %s: %s", self.base_url, exc)
                    return articles

                # Give JS a short moment to render, then wait for network idle
                try:
                    homepage.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass  # non-fatal

                article_urls = self._find_article_links(homepage)
                logger.info("Discovered %d article links on %s", len(article_urls), self.base_url)
                homepage.close()

                # ── 2. Visit each article page ──────────────────────────
                for url in article_urls:
                    page = None
                    try:
                        page = context.new_page()
                        page.goto(url, timeout=self.page_timeout, wait_until="domcontentloaded")
                        try:
                            page.wait_for_load_state("networkidle", timeout=10000)
                        except Exception:
                            pass

                        title = self._extract_title(page)
                        summary = self._extract_summary(page)

                        if title:
                            articles.append(Article(
                                title=title,
                                url=url,
                                published_at=datetime.now(timezone.utc),
                                description=summary,
                                source_name=self.source_name,
                            ))
                            logger.debug("Scraped: %s", title[:80])
                    except Exception as exc:
                        logger.warning("Failed to scrape %s: %s", url, exc)
                    finally:
                        if page is not None:
                            page.close()

                context.close()

        except Exception as exc:
            logger.error("Playwright error: %s", exc)
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

        logger.info("ScraplingPlaywrightCollector returned %d articles from %s", len(articles), self.base_url)
        return articles