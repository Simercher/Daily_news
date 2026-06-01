# news_feed_bootstrap

`news_feed_bootstrap` is the MVP RSS collection layer for Daily News. It turns curated RSS/OPML seed lists into active feed files and recent news-item JSONL for downstream agents or models.

This repository is intentionally **not** the final briefing bot. It prepares the raw material for later summarization, ranking, clustering, and Discord delivery.

## Current MVP Capabilities

The current pipeline can:

1. Import curated RSS/OPML seed lists from `configs/seed_sources.yaml`.
2. Keep future candidate sources in config with `enabled: false`.
3. Parse normal OPML and tolerate some malformed OPML, including unescaped ampersands, by falling back to outline-attribute extraction.
4. Run minimum RSS feed health checks.
5. Export active feeds as both JSON and OPML.
6. Fetch recent RSS items through local `feedparser`.
7. Deduplicate items by normalized exact URL.
8. Preserve a `collector` field so downstream stages can tell whether an item came from local feedparser or, later, an MCP collector.
9. Generate an RSS MCP config hint file for future/optional MCP handoff.
10. Run as agent-friendly scripts whose stdout is one final JSON object.

## Not Implemented Yet

This MVP does **not** currently:

- fetch through a real MCP stdio client;
- summarize articles with an LLM;
- classify items into final Daily News categories;
- rank importance or score credibility;
- cluster multiple sources into the same event;
- fetch full article text beyond RSS-provided content;
- bypass paywalls, CAPTCHAs, or access controls;
- post to Discord.

## Pipeline Shape

```text
configs/seed_sources.yaml
-> import enabled curated OPML/TXT feed lists
-> tolerant OPML parsing when strict XML fails
-> data/imported_feeds.json and data/imported_feeds.opml
-> minimum feed health check
-> data/active_feeds.json and data/active_feeds.opml
-> local RSS item fetch, or auto mode MCP-hint + local fallback
-> data/news_items_raw.jsonl
-> normalized exact-URL deduplication
-> data/news_items_deduped.jsonl
```

Primary outputs:

- `data/active_feeds.json`
- `data/active_feeds.opml`
- `data/news_items_raw.jsonl`
- `data/news_items_deduped.jsonl`
- `data/logs/mcp_config_hint.json`

Downstream systems should usually read:

```text
data/news_items_deduped.jsonl
```

## Install

Use `uv` from the repository root:

```bash
uv sync
```

For development tools and tests:

```bash
uv sync --dev
```

## Quick Run

One-shot MVP run:

```bash
uv run python scripts/agent_run_daily.py --mode auto --since-hours 24
```

`--mode auto` currently generates the MCP config hint, then uses local feedparser fallback because real MCP fetching is not implemented in this MVP.

Force a fresh bootstrap and keep validation runs short:

```bash
NEWS_FEED_TIMEOUT_SECONDS=3 uv run python scripts/agent_run_daily.py --mode auto --since-hours 24 --force-bootstrap
```

`NEWS_FEED_TIMEOUT_SECONDS` defaults to `15`. Use a shorter value for validation when slow RSS hosts would otherwise delay the run. Use the default or a higher value when completeness matters more than runtime.

## Human CLI

Human operators can also use the `news-feed` CLI:

```bash
uv run news-feed --help
uv run news-feed bootstrap
uv run news-feed fetch --mode local --since-hours 24
uv run news-feed dedup
uv run news-feed run-all --mode local --since-hours 24
```

Agents should prefer `scripts/agent_*.py` because script stdout is machine-readable JSON.

## Agent Documentation

The canonical agent runbook is:

```text
docs/agent_handoff.md
```

Hermes-specific notes are intentionally kept short and non-duplicative in:

```text
docs/hermes_agent_workflow.md
```

## Seed Sources

Feed sources are configured in:

```text
configs/seed_sources.yaml
```

Currently enabled source families:

- `feedsForJournalists` OPML
- `plenaryapp/awesome-rss-feeds` United States / United Kingdom
- `awesome-tech-rss`

Currently retained but disabled candidates:

- `feedsForJournalists` text list, mostly overlapping fallback
- `SecurityRSS`, for a future cybersecurity section
- `awesome_ML_AI_RSS_feed`, for future AI/ML specialist runs
- `awesome-newsCN-feeds`, because Chinese third-party/generated feeds need extra review

Sources with `enabled: false` stay documented in config but are skipped by bootstrap.

## MCP Handoff

Generate an MCP config hint:

```bash
uv run python scripts/agent_generate_mcp_config.py --server imprvhub_mcp_rss_aggregator
```

The generated hint is written to:

```text
data/logs/mcp_config_hint.json
```

Expected MVP behavior:

- `--mode auto`: writes the MCP hint and falls back to local feedparser.
- `--mode local`: uses local feedparser only.
- `--mode mcp`: writes the MCP hint, returns `ok: false`, and exits with code `3` because real MCP fetching is not implemented yet.

Hermes native MCP status for this environment:

- `/opt/data/config.yaml` has `mcp_servers.rssAggregator` pointing at `external/mcp-rss-aggregator/build/index.js` with `FEEDS_PATH=data/active_feeds.opml`.
- `hermes mcp test rssAggregator` connects and discovers one `rss` tool.
- The Daily_news Python pipeline still does not call that MCP tool directly; until a stdio MCP client/normalizer is added, pipeline `--mode auto` intentionally keeps using local feedparser and records `collector: "local_feedparser"`.

## Tests

```bash
uv run pytest -q
uv run ruff check src scripts tests
uv build
```

## Legacy

The old source governance workflow lives in `legacy/old_governance/` for reference. It is not part of the MVP runtime path.
