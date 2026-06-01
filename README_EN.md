# news_feed_bootstrap

`news_feed_bootstrap` is a lightweight RSS bootstrap layer for daily news collection.

The MVP flow is:

```text
GitHub curated RSS/OPML lists
-> import feed_url candidates
-> minimum health check
-> data/active_feeds.opml and data/active_feeds.json
-> local feedparser fetch or external RSS MCP server
-> data/news_items_raw.jsonl
-> downstream model handles dedup, classification, importance, and summaries
```

This project intentionally does not run LLM calls, Discord bots, Playwright, homepage feed discovery, source credibility scoring, paywall bypassing, login-wall bypassing, or Cloudflare/captcha workarounds.

## Install

```bash
cd /Users/linyuzhan/Documents/.data/daily_news
export UV_CACHE_DIR=.uv-cache
export UV_PYTHON_INSTALL_DIR=.uv-python
uv sync
uv sync --dev
```

Quick checks:

```bash
uv run news-feed --help
uv run python -m news_feed_bootstrap.cli --help
uv run python scripts/agent_run_daily.py --mode local --since-hours 24
```

## Configure Seed Sources

Edit `configs/seed_sources.yaml`.

Seed URLs should be direct `raw.githubusercontent.com` OPML or text files whenever possible. GitHub pages and web directories are kept as notes until their raw paths are manually confirmed.

Included seeds:

- `feedsForJournalists`: OPML and text list, high priority.
- `plenaryapp/awesome-rss-feeds`: United States and United Kingdom OPML examples, medium-high priority.
- `awesome-tech-rss`: technology, AI, startup, and engineering OPML, medium priority.
- `SecurityRSS`: listed as a manual-confirmation source because the raw feed list path is not pinned yet.

## Bootstrap Feeds

```bash
uv run news-feed bootstrap
```

This imports seed sources into `data/imported_feeds.json`, runs minimum health checks, and writes:

- `data/feed_health.jsonl`
- `data/active_feeds.json`
- `data/active_feeds.opml`

Only feeds with an active, parseable feed and recent items are written to the active outputs.

You can also run the steps separately:

```bash
uv run news-feed bootstrap-seeds
uv run news-feed health-check
```

## Local Fetch Mode

Local mode does not start MCP. It uses `feedparser` directly as a test and fallback path:

```bash
uv run news-feed fetch --mode local --since-hours 24
uv run news-feed dedup
```

Output:

- `data/news_items_raw.jsonl`

The output is raw RSS item data. Downstream model stages should handle classification, importance, clustering, and summaries.

## MCP Mode

The first version provides an MCP adapter abstraction and exports `data/active_feeds.opml` for external RSS MCP servers.

```bash
uv run news-feed mcp-notes
```

Candidate MCP servers:

- `rss-reader-mcp`: RSS aggregation and article content extraction.
- `buhe/mcp_rss`: OPML import and long-term storage; requires MySQL.
- `imprvhub/mcp-rss-aggregator`: OPML import, category filtering, latest articles.
- `veithly/rss-mcp`: generic RSS/Atom parser and RSSHub-compatible feeds.

The stdio MCP client is intentionally left as a TODO until the target RSS MCP server is selected.

## Hermes Agent Usage

Hermes agent should use `scripts/agent_*.py`. Human operators may use the `news-feed` CLI.

Agent stdout is JSON-only. Logs are written to `data/logs/`.

```bash
uv run python scripts/agent_status.py
uv run python scripts/agent_bootstrap.py
uv run python scripts/agent_generate_mcp_config.py --server imprvhub_mcp_rss_aggregator
uv run python scripts/agent_fetch_latest.py --mode local --since-hours 24
uv run python scripts/agent_dedup.py
uv run python scripts/agent_run_daily.py --mode local --since-hours 24
```

Daily run bootstraps automatically when `data/active_feeds.json` or `data/active_feeds.opml` is missing or older than 24 hours.

See `docs/hermes_agent_workflow.md` for the standard Hermes workflow and JSON contract.

## Legacy

The old source governance workflow was moved to `legacy/old_governance/`. It includes the previous homepage discovery, `source_score` / `feed_score`, `approved_feeds.yaml`, article extraction, and related tests. It is kept only as reference and is not part of the MVP CLI.
