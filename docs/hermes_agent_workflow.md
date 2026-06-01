# Hermes Agent Workflow

Hermes should use the `scripts/agent_*.py` entrypoints. Their stdout is JSON-only, and logs are written to `data/logs/`.

## Standard Local Flow

```text
Step 1. uv sync
Step 2. uv run python scripts/agent_bootstrap.py
Step 3. uv run python scripts/agent_generate_mcp_config.py --server imprvhub_mcp_rss_aggregator
Step 4. Start or confirm the RSS MCP server if MCP mode is needed
Step 5. uv run python scripts/agent_fetch_latest.py --mode local --since-hours 24
Step 6. uv run python scripts/agent_dedup.py
Step 7. Read data/news_items_deduped.jsonl
Step 8. Pass the items to the downstream model for classification, cross-source deduplication, summarization, and importance ranking
```

The first version defaults to local mode. Local mode uses Python `feedparser` and does not require an MCP server.

## Optional MCP Mode

```bash
uv run python scripts/agent_fetch_latest.py --mode mcp --server imprvhub_mcp_rss_aggregator --since-hours 24
```

MCP mode is adapter-only in this MVP. The script writes `data/logs/mcp_config_hint.json`, returns a JSON error with exit code `3`, and includes a warning that local mode is available as fallback.

## Daily Run

```bash
uv run python scripts/agent_run_daily.py --mode local --since-hours 24
```

`agent_run_daily.py` bootstraps automatically when `data/active_feeds.json` or `data/active_feeds.opml` is missing or older than 24 hours.

Options:

- `--force-bootstrap`: always rebuild imported and active feed files.
- `--skip-bootstrap`: use existing active feed files.

## JSON Contract

Successful scripts return:

```json
{
  "ok": true,
  "command": "agent_status",
  "message": "Project status collected.",
  "outputs": {},
  "stats": {},
  "warnings": []
}
```

Failures return:

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
