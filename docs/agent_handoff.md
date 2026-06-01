# Agent Handoff Guide

This document is for an automation agent that has just cloned this repository.

If the caller is specifically Hermes, also read `docs/hermes_agent_workflow.md` after this file. That file is the Hermes-specific runbook; this file is the general project handoff.

The project is an RSS feed bootstrap and raw news collection layer. It does not call LLM APIs, summarize articles, run Discord delivery, bypass paywalls, or perform event clustering. Its job is to prepare active RSS feeds and produce JSONL records for downstream models.

## What This Project Does

Pipeline:

```text
configs/seed_sources.yaml
-> import curated OPML/TXT feed lists
-> data/imported_feeds.json and data/imported_feeds.opml
-> minimum feed health check
-> data/active_feeds.json and data/active_feeds.opml
-> fetch latest RSS items
-> data/news_items_raw.jsonl
-> deduplicate and normalize output
-> data/news_items_deduped.jsonl
```

Use local mode first. MCP mode is prepared through config hints, but the stdio MCP client is not implemented in this MVP.

## First Steps After Clone

Run from the repository root:

```bash
uv sync
uv run python scripts/agent_status.py
```

All `scripts/agent_*.py` commands print one final JSON object to stdout. Do not parse human logs. Logs are written to `data/logs/`.

## Standard Daily Flow

```bash
uv run python scripts/agent_bootstrap.py
uv run python scripts/agent_generate_mcp_config.py --server imprvhub_mcp_rss_aggregator
uv run python scripts/agent_fetch_latest.py --mode local --since-hours 24
uv run python scripts/agent_dedup.py
```

Equivalent one-shot local run:

```bash
uv run python scripts/agent_run_daily.py --mode local --since-hours 24
```

`agent_run_daily.py` bootstraps automatically when `data/active_feeds.json` or `data/active_feeds.opml` is missing or older than 24 hours.

Hermes-specific sequencing and fallback behavior are documented in `docs/hermes_agent_workflow.md`.

Useful options:

```bash
uv run python scripts/agent_run_daily.py --mode local --since-hours 24 --force-bootstrap
uv run python scripts/agent_run_daily.py --mode local --since-hours 24 --skip-bootstrap
```

Do not use `--force-bootstrap` and `--skip-bootstrap` together.

## MCP Handoff

Generate config hints:

```bash
uv run python scripts/agent_generate_mcp_config.py --server imprvhub_mcp_rss_aggregator
```

Output:

```text
data/logs/mcp_config_hint.json
```

Supported server IDs:

- `imprvhub_mcp_rss_aggregator`
- `buhe_mcp_rss`
- `rss_reader_mcp`
- `veithly_rss_mcp`

Optional MCP fetch command:

```bash
uv run python scripts/agent_fetch_latest.py --mode mcp --server imprvhub_mcp_rss_aggregator --since-hours 24
```

Expected MVP behavior: the script writes `data/logs/mcp_config_hint.json`, returns JSON with `ok: false`, and exits with code `3`. The JSON warning tells the caller that local mode is available as fallback.

## JSON Contract

Success shape:

```json
{
  "ok": true,
  "command": "agent_run_daily",
  "message": "Daily RSS pipeline completed.",
  "outputs": {},
  "stats": {},
  "warnings": []
}
```

Failure shape:

```json
{
  "ok": false,
  "command": "agent_fetch_latest",
  "message": "RSS fetch failed.",
  "error": {
    "type": "ExternalServiceError",
    "detail": "MCP server is not reachable."
  },
  "outputs": {},
  "stats": {},
  "warnings": ["Fallback to local mode is available."]
}
```

Exit codes:

- `0`: success
- `1`: recoverable error
- `2`: configuration error
- `3`: external service or MCP error

## Important Files

- `configs/seed_sources.yaml`: curated OPML/TXT sources.
- `data/imported_feeds.json`: imported feed candidates.
- `data/feed_health.jsonl`: feed health check results.
- `data/active_feeds.json`: active feed metadata.
- `data/active_feeds.opml`: OPML handoff file for RSS MCP servers.
- `data/news_items_raw.jsonl`: raw RSS item output.
- `data/news_items_deduped.jsonl`: downstream model input.
- `data/logs/*.log`: script logs.
- `data/logs/mcp_config_hint.json`: generated MCP config hint.

## Downstream Model Input

Read:

```text
data/news_items_deduped.jsonl
```

Each row is shaped for downstream classification, cross-source deduplication, importance ranking, summarization, and Discord formatting. Do not expect this project to perform those semantic tasks.

## Human CLI

Humans may use:

```bash
uv run news-feed --help
uv run news-feed bootstrap
uv run news-feed fetch --mode local --since-hours 24
uv run news-feed dedup
uv run news-feed run-all --mode local --since-hours 24
```

Agents should prefer `scripts/agent_*.py` because stdout is JSON-only.

## Troubleshooting

If `imported_feeds`, `active_feeds`, and item counts are `0`, check whether the runtime can reach `raw.githubusercontent.com` and RSS feed hosts. The scripts still return machine-readable JSON and may include warnings.

If MCP mode fails, use local mode:

```bash
uv run python scripts/agent_fetch_latest.py --mode local --since-hours 24
```
