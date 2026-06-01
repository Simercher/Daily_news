# Agent Handoff Runbook

This is the canonical automation-agent runbook for the Daily News RSS MVP.

Use this file for all non-human execution instructions. `docs/hermes_agent_workflow.md` is only a short Hermes-specific overlay and must not duplicate this runbook.

## Scope

This project is an RSS feed bootstrap and raw news collection layer.

It prepares:

- active RSS feed metadata;
- active feed OPML for future MCP handoff;
- raw RSS item JSONL;
- deduplicated downstream JSONL.

It does **not** summarize, classify, rank, cluster, call LLM APIs, post to Discord, fetch paywalled content, bypass access controls, or run a real MCP stdio RSS client yet.

## Runtime Contract

Run commands from the repository root.

Agents should use `scripts/agent_*.py`, not the human-oriented `news-feed` CLI, because agent scripts print one final JSON object to stdout and write logs to `data/logs/`.

Rules:

1. Parse the final stdout JSON object, not human logs.
2. Treat `ok: true` as success.
3. Treat `ok: false` with exit code `2` as configuration failure.
4. Treat `ok: false` with exit code `3` as external-service/MCP failure; local fallback is usually allowed.
5. If item counts are `0`, inspect `warnings` and network access to `raw.githubusercontent.com` / RSS hosts.

Exit codes:

- `0`: success
- `1`: recoverable runtime error
- `2`: configuration error
- `3`: external service or MCP error

## Pipeline

```text
configs/seed_sources.yaml
-> import enabled curated OPML/TXT feed lists
-> strict OPML parse, with tolerant xmlUrl/htmlUrl/title/text fallback for malformed OPML
-> data/imported_feeds.json and data/imported_feeds.opml
-> minimum feed health check
-> data/active_feeds.json and data/active_feeds.opml
-> local RSS item fetch, or auto mode MCP-hint + local fallback
-> data/news_items_raw.jsonl
-> normalized exact-URL deduplication
-> data/news_items_deduped.jsonl
```

## First Steps After Clone

```bash
uv sync
uv run python scripts/agent_status.py
```

If dependencies for development checks are missing:

```bash
uv sync --dev
```

## Recommended One-Shot Run

Use this for normal automation:

```bash
uv run python scripts/agent_run_daily.py --mode auto --since-hours 24
```

Behavior:

- bootstraps automatically if `data/active_feeds.json` or `data/active_feeds.opml` is missing or older than 24 hours;
- writes `data/logs/mcp_config_hint.json`;
- fetches through local feedparser because real MCP fetch is not implemented yet;
- deduplicates into `data/news_items_deduped.jsonl`.

## Step-by-Step Run

Use this when the agent needs explicit checkpoints:

```bash
uv run python scripts/agent_bootstrap.py
uv run python scripts/agent_generate_mcp_config.py --server imprvhub_mcp_rss_aggregator
uv run python scripts/agent_fetch_latest.py --mode local --since-hours 24
uv run python scripts/agent_dedup.py
```

## Bootstrap and Timeout Controls

```bash
uv run python scripts/agent_run_daily.py --mode auto --since-hours 24 --force-bootstrap
uv run python scripts/agent_run_daily.py --mode auto --since-hours 24 --skip-bootstrap
NEWS_FEED_TIMEOUT_SECONDS=3 uv run python scripts/agent_run_daily.py --mode auto --since-hours 24 --force-bootstrap
```

Constraints:

- Do not combine `--force-bootstrap` and `--skip-bootstrap`.
- `NEWS_FEED_TIMEOUT_SECONDS` defaults to `15`.
- Use a short timeout for validation if slow RSS hosts would otherwise exceed the automation budget.
- Use the default or a higher timeout when completeness matters more than runtime.

## MCP Modes

Supported server IDs for config hints:

- `imprvhub_mcp_rss_aggregator`
- `buhe_mcp_rss`
- `rss_reader_mcp`
- `veithly_rss_mcp`

Generate only the config hint:

```bash
uv run python scripts/agent_generate_mcp_config.py --server imprvhub_mcp_rss_aggregator
```

Expected mode behavior:

| Mode | Command shape | Expected MVP behavior |
| --- | --- | --- |
| `local` | `agent_fetch_latest.py --mode local --since-hours 24` | Fetches with local feedparser. |
| `auto` | `agent_fetch_latest.py --mode auto --server imprvhub_mcp_rss_aggregator --since-hours 24` | Writes MCP hint, warns, falls back to local feedparser, exits `0`. |
| `mcp` | `agent_fetch_latest.py --mode mcp --server imprvhub_mcp_rss_aggregator --since-hours 24` | Writes MCP hint, returns `ok: false`, exits `3`. |

Do not treat `--mode mcp` exit code `3` as an unexpected regression in this MVP. It is the documented behavior until a real MCP stdio client is implemented.

Hermes native MCP status in the current deployment:

- `/opt/data/config.yaml` contains `mcp_servers.rssAggregator` with command `node`, args `/opt/data/plugins/Daily_news/external/mcp-rss-aggregator/build/index.js`, and env `FEEDS_PATH=/opt/data/plugins/Daily_news/data/active_feeds.opml`.
- `hermes mcp test rssAggregator` should connect and discover one `rss` tool.
- This validates that the MCP server can run under Hermes, but the Daily_news Python pipeline still does not call the MCP tool directly. Until a stdio MCP client and output normalizer are implemented, `--mode auto` remains the correct automation default and should produce `collector: "local_feedparser"`.

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

## Important Files

| Path | Purpose |
| --- | --- |
| `configs/seed_sources.yaml` | Curated OPML/TXT seed sources; `enabled: false` keeps candidates without importing them. |
| `data/imported_feeds.json` | Imported feed candidates. |
| `data/imported_feeds.opml` | Imported feed candidates as OPML. |
| `data/feed_health.jsonl` | Feed health check results. |
| `data/active_feeds.json` | Active feed metadata. |
| `data/active_feeds.opml` | OPML handoff file for RSS MCP servers. |
| `data/inactive_feeds.json` | Inactive or failed feed candidates plus health information. |
| `data/news_items_raw.jsonl` | Raw RSS item output. |
| `data/news_items_deduped.jsonl` | Main downstream model/agent input. |
| `data/logs/*.log` | Script logs. |
| `data/logs/mcp_config_hint.json` | Generated MCP config hint. |

Downstream agents should usually read:

```text
data/news_items_deduped.jsonl
```

Rows include `collector`, currently `local_feedparser`. Future MCP integration should write `collector: "mcp:<server_id>"`.

## Source Configuration

Currently enabled families:

- `feedsForJournalists` OPML
- `plenaryapp/awesome-rss-feeds` United States / United Kingdom
- `awesome-tech-rss`

Currently disabled candidates:

- `feedsForJournalists` text list
- `SecurityRSS`
- `awesome_ML_AI_RSS_feed`
- `awesome-newsCN-feeds`

Only enable disabled candidates after checking source quality and whether the downstream briefing needs that topic.

## Validation Commands

```bash
uv run pytest -q
uv run ruff check src scripts tests
uv build
```

For an end-to-end validation run:

```bash
NEWS_FEED_TIMEOUT_SECONDS=3 uv run python scripts/agent_run_daily.py --mode auto --server imprvhub_mcp_rss_aggregator --since-hours 24 --force-bootstrap
```

## Troubleshooting

- `imported_feeds`, `active_feeds`, or item counts are `0`: check network access to GitHub raw URLs and RSS hosts.
- Forced bootstrap takes too long: use `NEWS_FEED_TIMEOUT_SECONDS=3` for validation.
- `--mode mcp` exits `3`: expected MVP behavior; use `--mode auto` or `--mode local`.
- JSON says `ok: false`: inspect `error.type`, `error.detail`, and `warnings` before retrying.
