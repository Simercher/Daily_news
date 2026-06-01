# Hermes Agent Runbook

This file is the Hermes-specific execution runbook. For the general project overview, file map, JSON contract, and troubleshooting notes, read `docs/agent_handoff.md` first.

Hermes should use `scripts/agent_*.py`, not the human-oriented `news-feed` CLI. Agent script stdout is JSON-only. Logs are written to `data/logs/`.

## Default Local Run

Run from the repository root:

```bash
uv sync
uv run python scripts/agent_status.py
uv run python scripts/agent_run_daily.py --mode local --since-hours 24
```

`agent_run_daily.py` is the preferred Hermes entrypoint for normal operation. It will bootstrap automatically when `data/active_feeds.json` or `data/active_feeds.opml` is missing or older than 24 hours.

## Step-By-Step Run

Use this when Hermes wants explicit checkpoints between stages:

```bash
uv run python scripts/agent_bootstrap.py
uv run python scripts/agent_generate_mcp_config.py --server imprvhub_mcp_rss_aggregator
uv run python scripts/agent_fetch_latest.py --mode local --since-hours 24
uv run python scripts/agent_dedup.py
```

Final downstream input:

```text
data/news_items_deduped.jsonl
```

## Bootstrap Controls

```bash
uv run python scripts/agent_run_daily.py --mode local --since-hours 24 --force-bootstrap
uv run python scripts/agent_run_daily.py --mode local --since-hours 24 --skip-bootstrap
```

Do not combine `--force-bootstrap` and `--skip-bootstrap`.

## MCP Handoff

MCP mode is not a full stdio client in this MVP. Hermes can still generate config hints:

```bash
uv run python scripts/agent_generate_mcp_config.py --server imprvhub_mcp_rss_aggregator
```

Output:

```text
data/logs/mcp_config_hint.json
```

If Hermes tries MCP fetch:

```bash
uv run python scripts/agent_fetch_latest.py --mode mcp --server imprvhub_mcp_rss_aggregator --since-hours 24
```

Expected MVP behavior:

- stdout JSON has `ok: false`
- exit code is `3`
- `data/logs/mcp_config_hint.json` is written
- warning says local mode is available as fallback

Fallback command:

```bash
uv run python scripts/agent_fetch_latest.py --mode local --since-hours 24
```

## Decision Rules

- If stdout JSON has `ok: true`, Hermes may continue to the next step.
- If `ok: false` and exit code is `2`, treat it as a configuration issue.
- If `ok: false` and exit code is `3`, treat it as MCP or external-service failure and fallback to local mode when appropriate.
- If counts are `0`, inspect JSON `warnings`; common cause is missing network access to `raw.githubusercontent.com` or RSS feed hosts.
