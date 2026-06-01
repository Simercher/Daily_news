# Hermes Agent Workflow Overlay

This file is intentionally short. The canonical agent runbook is `docs/agent_handoff.md`.

Hermes agents should read `docs/agent_handoff.md` first and use this file only for Hermes-specific routing choices.

## Hermes Defaults

Use the agent scripts, not the human CLI:

```bash
uv run python scripts/agent_status.py
uv run python scripts/agent_run_daily.py --mode auto --since-hours 24
```

## Hermes Decision Rules

- If stdout JSON has `ok: true`, continue.
- If `ok: false` with exit code `2`, report a configuration problem.
- If `ok: false` with exit code `3`, treat it as an MCP/external-service limitation and fallback to `--mode auto` or `--mode local`.
- `rssAggregator` is configured in `/opt/data/config.yaml`; verify it with `hermes mcp test rssAggregator` when MCP availability matters.
- Direct `rssAggregator` MCP smoke works in this environment: the server loads the active OPML and `latest --5` returns items.
- The local ignored `external/mcp-rss-aggregator` patch fixes same-domain feed ID collisions by using host + path/query + a short URL hash for feed IDs.
- `external/` is gitignored; do not commit or fork it in this step. Preserve the MCP patch later via upstream/fork or an explicit setup patch if needed.
- Even when `rssAggregator` is available, this MVP Python pipeline still uses local feedparser in `--mode auto` until a stdio MCP client/normalizer is added.
- Do not edit Hermes `config.yaml` unless the user explicitly asks for MCP installation/configuration or the configured `rssAggregator` path/env is stale.
