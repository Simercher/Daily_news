# Hermes Agent Workflow Overlay

This file is intentionally short. The canonical agent runbook is `docs/agent_handoff.md`.

Hermes agents should read `docs/agent_handoff.md` first and use this file only for Hermes-specific routing choices.

## Hermes Defaults

Use the agent scripts, not the human CLI:

```bash
uv run python scripts/agent_status.py
uv run python scripts/agent_run_daily.py --mode auto --since-hours 24
```

Why `--mode auto`:

- it generates `data/logs/mcp_config_hint.json` for future MCP handoff;
- it falls back to local feedparser because real MCP stdio fetching is not implemented in this MVP;
- it exits successfully when local fallback works.

## Hermes Validation Run

When Hermes needs to prove the full pipeline works in a bounded automation window, use a shorter RSS request timeout:

```bash
NEWS_FEED_TIMEOUT_SECONDS=3 uv run python scripts/agent_run_daily.py --mode auto --server imprvhub_mcp_rss_aggregator --since-hours 24 --force-bootstrap
```

Use the default timeout for production-like collection when runtime is less constrained.

## Hermes Decision Rules

- If stdout JSON has `ok: true`, continue.
- If `ok: false` with exit code `2`, report a configuration problem.
- If `ok: false` with exit code `3`, treat it as an MCP/external-service limitation and fallback to `--mode auto` or `--mode local`.
- `rssAggregator` is configured in `/opt/data/config.yaml`; verify it with `hermes mcp test rssAggregator` when MCP availability matters.
- Even when `rssAggregator` is available, this MVP pipeline still uses local feedparser in `--mode auto` until a stdio MCP client/normalizer is added.
- Do not edit Hermes `config.yaml` unless the user explicitly asks for MCP installation/configuration or the configured `rssAggregator` path/env is stale.

## No Duplicate Runbook Content

Do not add general pipeline instructions, file maps, JSON schemas, or troubleshooting tables here. Put those in `docs/agent_handoff.md` so future agents have one source of truth.
