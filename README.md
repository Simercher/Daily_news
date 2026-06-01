# news_feed_bootstrap

`news_feed_bootstrap` is a small automation project for turning curated RSS/OPML lists into clean feed and news-item files.

It is designed as the collection layer before a downstream model pipeline. This project gathers RSS feeds, checks whether they are usable, fetches recent RSS items, and writes JSON/JSONL outputs. It does not summarize, classify, rank, cluster, call LLM APIs, run Discord delivery, use Playwright, or bypass paywalls and access controls.

## How To Think About It

```text
curated RSS/OPML lists
-> imported feed candidates
-> minimum health check
-> active feeds JSON/OPML
-> raw RSS item fetch
-> deduped JSONL for downstream models
```

Primary outputs:

- `data/active_feeds.json`
- `data/active_feeds.opml`
- `data/news_items_raw.jsonl`
- `data/news_items_deduped.jsonl`

## Install

Use `uv` from the repository root:

```bash
uv sync
```

For development tools and tests:

```bash
uv sync --dev
```

## Human CLI

Human operators can use the `news-feed` CLI:

```bash
uv run news-feed --help
uv run news-feed bootstrap
uv run news-feed fetch --mode local --since-hours 24
uv run news-feed dedup
uv run news-feed run-all --mode local --since-hours 24
```

`run-all` performs bootstrap, local fetch, and deduplication in one command.

## Agent Entry Points

Automation agents should use the scripts in `scripts/`. Their stdout is JSON-only, and logs are written to `data/logs/`.

```bash
uv run python scripts/agent_status.py
uv run python scripts/agent_bootstrap.py
uv run python scripts/agent_run_daily.py --mode local --since-hours 24
```

For a full agent handoff guide, see `docs/agent_handoff.md`.

## Seed Sources

Feed sources are configured in:

```text
configs/seed_sources.yaml
```

Seed URLs should be direct OPML or text files when possible. GitHub pages and web directories are kept as notes until their raw paths are confirmed.

Included seed families:

- `feedsForJournalists`
- `plenaryapp/awesome-rss-feeds`
- `awesome-tech-rss`
- `SecurityRSS` as a manual-confirmation source

## MCP Handoff

This MVP prepares bridge files for external RSS MCP servers:

```bash
uv run news-feed mcp-config --server imprvhub_mcp_rss_aggregator
```

The generated hint is written to:

```text
data/logs/mcp_config_hint.json
```

MCP fetch is adapter-only in this MVP. Local mode is the default working path.

## Tests

```bash
uv run pytest
uv run ruff check src scripts tests
```

## Legacy

The old source governance workflow lives in `legacy/old_governance/` for reference. It is not part of the MVP runtime path.
