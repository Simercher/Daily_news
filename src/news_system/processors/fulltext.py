"""Full-text extraction for news articles using trafilatura.

Fetches article HTML from URLs and extracts the main content text.
Designed to run as a post-fetch step before dedup/storage.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Iterable

import httpx
import trafilatura

from news_system.processors.fulltext_quality import compute_fulltext_quality

log = logging.getLogger(__name__)

_MAX_WORKERS = 8          # concurrent fetches
_MAX_TEXT_LENGTH = 50_000  # cap extracted text
_REQUEST_TIMEOUT = 20      # per-URL timeout


def extract_articles(
    articles: Iterable,
    *,
    max_workers: int = _MAX_WORKERS,
    timeout: int = _REQUEST_TIMEOUT,
    user_agent: str = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Daily_news/0.1",
) -> list:
    """Fetch and extract full text for articles that lack content.

    Accepts any iterable of objects with ``url``, ``content`` (set-able),
    ``description``, and ``raw`` (dict) attributes.

    Returns the same list (modified in place) so the caller can continue
    the pipeline without re-assigning.
    """
    articles = list(articles)
    pending = [a for a in articles if a.url and not getattr(a, "content", None)]

    if not pending:
        return articles

    client = httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": user_agent},
    )

    def _extract_one(article):
        now = datetime.now(timezone.utc)
        # Set initial status
        article.fulltext_status = "not_attempted"
        article.fulltext_extracted_at = now
        article.fulltext_quality_score = 0.0
        article.fulltext_error_message = None

        try:
            resp = client.get(article.url)

            # Check for blocked HTTP status codes
            if resp.status_code in (403, 429, 451):
                raw = dict(getattr(article, "raw", {}) or {})
                raw["fulltext_status"] = "blocked"
                article.raw = raw
                article.fulltext_status = "blocked"
                article.fulltext_quality_score = 0.0
                article.fulltext_extracted_at = now
                article.fulltext_error_message = f"HTTP {resp.status_code}"
                return article

            resp.raise_for_status()

            # Check for paywalled content before extraction
            if "ONLY AVAILABLE IN PAID PLANS" in resp.text:
                raw = dict(getattr(article, "raw", {}) or {})
                raw["fulltext_status"] = "paywalled"
                article.raw = raw
                article.fulltext_status = "paywalled"
                article.fulltext_quality_score = 0.2
                article.fulltext_extracted_at = now
                return article

            text = trafilatura.extract(
                resp.text,
                include_comments=False,
                include_tables=False,
                include_images=False,
                include_formatting=False,
                no_fallback=False,
                output_format="txt",
            )

            if text and text.strip():
                text = text.strip()[:min(len(text.strip()), _MAX_TEXT_LENGTH)]
                article.content = text
                quality, length = compute_fulltext_quality(text, status="extracted")

                # Determine status based on length
                if length < 300:
                    fts = "partial"
                else:
                    fts = "extracted"

                raw = dict(getattr(article, "raw", {}) or {})
                raw["fulltext_status"] = fts
                raw["fulltext_length"] = length
                article.raw = raw
                article.fulltext_status = fts
                article.fulltext_quality_score = quality
                article.fulltext_extracted_at = now
            else:
                raw = dict(getattr(article, "raw", {}) or {})
                raw["fulltext_status"] = "empty"
                article.raw = raw
                article.fulltext_status = "empty"
                article.fulltext_quality_score = 0.0
                article.fulltext_extracted_at = now

        except httpx.TimeoutException:
            raw = dict(getattr(article, "raw", {}) or {})
            raw["fulltext_status"] = "timeout"
            article.raw = raw
            article.fulltext_status = "timeout"
            article.fulltext_quality_score = 0.0
            article.fulltext_extracted_at = now
            article.fulltext_error_message = "timeout"
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            fts = "blocked" if status in (403, 429, 451) else "error"
            raw = dict(getattr(article, "raw", {}) or {})
            raw["fulltext_status"] = fts
            article.raw = raw
            article.fulltext_status = fts
            article.fulltext_quality_score = 0.0
            article.fulltext_extracted_at = now
            article.fulltext_error_message = str(e)[:200]
        except Exception as exc:
            error_msg = str(exc)[:200]
            raw = dict(getattr(article, "raw", {}) or {})
            raw["fulltext_status"] = "error"
            article.raw = raw
            article.fulltext_status = "error"
            article.fulltext_quality_score = 0.0
            article.fulltext_extracted_at = now
            article.fulltext_error_message = error_msg
            raw["fulltext_error"] = error_msg
            article.raw = raw

        return article

    done_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_extract_one, a): a for a in pending}
        for f in as_completed(futures):
            done_count += 1
            if done_count % 50 == 0:
                log.info("fulltext extraction progress: %d/%d", done_count, len(pending))
            try:
                f.result()
            except Exception as exc:
                log.warning("unexpected fulltext error: %s", exc)

    client.close()

    ok = sum(1 for a in pending if getattr(a, "fulltext_status", None) in ("extracted", "partial"))
    errors = sum(1 for a in pending if getattr(a, "fulltext_status", None) in ("error", "timeout", "blocked"))
    log.info(
        "fulltext extraction done: %d/%d extracted, %d errors, %d skipped",
        ok, len(pending), errors, len(articles) - len(pending),
    )
    return articles