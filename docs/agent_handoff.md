# Agent Handoff Runbook

This is the canonical automation-agent runbook for the Daily News RSS MVP.

Use this file for all non-human execution instructions. `docs/hermes_agent_workflow.md` is only a short Hermes-specific overlay and must not duplicate this runbook.

## Scope

This project is an RSS feed bootstrap and raw news collection layer.

It prepares:

- active RSS feed metadata;
- conservative `official_source` provenance on feeds and items;
- active feed OPML for future MCP handoff;
- raw RSS item JSONL;
- deduplicated downstream JSONL;
- deterministic exact-URL deduplication output;
- downstream semantic labels from `profiles/domain-classifier`, including daily section routing and same-event cluster metadata;
- a structured fulltext-fetch manifest for `rss_reader_mcp`.

It does **not** summarize, rank, call LLM APIs from the Python RSS pipeline, post to Discord, fetch paywalled content, bypass access controls, or run a real MCP stdio RSS client yet.

Semantic domain classification and title-similarity same-event clustering are delegated to the Hermes `profiles/domain-classifier` agent after `data/news_items_deduped.jsonl` exists.

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
-> conservative official_source marking from configs/official_sources.yaml
-> local RSS item fetch, or MCP-first fetch with local fallback
-> data/news_items_raw.jsonl
-> normalized exact-URL deduplication
-> data/news_items_deduped.jsonl
-> domain-classifier semantic labeling
-> data/news_item_labels.jsonl
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
uv run python scripts/agent_classify_articles.py
uv run python scripts/agent_fetch_fulltext.py
```

After this, downstream aggregation agents should read `data/news_item_fulltext.jsonl` rather than the manifest alone.

The classifier output is the first layer that should contain:

- `daily_section`: `international`, `macro`, `stocks`, `tech_ai`, or `other`;
- `event_cluster_id`: stable same-event cluster ID for this batch;
- `event_primary_article_id`: representative article for the cluster;
- `duplicate_of_article_id`: `null` for the primary article, otherwise the cluster primary article ID;
- `same_event_confidence` and `same_event_reason`.

The classifier must not edit `data/news_items_deduped.jsonl`; it writes labels beside it so downstream ranking/digest generation can choose one primary article per event cluster while retaining supporting sources.

## Fulltext Fetch Contract

`rss_reader_mcp` is the next-stage MCP server for fulltext extraction. Its GitHub source is:

```text
https://github.com/kwp-lab/rss-reader-mcp.git
```

The repo should be placed under `external/rss-reader-mcp/` in the same style as `external/mcp-rss-aggregator/`.

### Fulltext stage purpose

`rss_reader_mcp` does **not** classify or summarize. It only:

1. reads `data/news_item_labels.jsonl`;
2. fetches article fulltext using the manifest's URLs and hints;
3. writes a fulltext-enriched JSONL for later aggregation agents.

### Fulltext input

Primary input:

```text
data/news_item_labels.jsonl
```

Every row should include at least:

- `article_id`
- `url`
- `canonical_url`
- `feed_url`
- `title`
- `published_at`
- `collector`
- `official_source`
- `language`
- `dedupe_key`
- `same_event_cluster_id`
- `same_event_cluster_rank`
- `same_event_cluster_size`
- `same_event_cluster_primary_id`
- `primary_domain`
- `secondary_domains`
- `topics`
- `entities`
- `content_type`
- `geography`
- `confidence`
- `needs_human_review`
- `fetch_required`
- `fetch_priority`
- `fetch_hints`

`fetch_hints` should be an object that can carry preferences such as:

- `prefer_fulltext`
- `prefer_primary_source`
- `prefer_canonical_url`
- `cluster_primary`
- `allow_redirects`

### Fulltext output

Primary output:

```text
data/news_item_fulltext.jsonl
```

Each output row should preserve the manifest fields above and add:

- `fulltext`
- `fulltext_source`
- `fulltext_fetched_at`
- `fulltext_status`
- `fulltext_word_count`
- `fulltext_language`
- `fulltext_excerpt`
- `fetch_attempted`
- `fetch_error`

Recommended `fulltext_status` values:

- `success`
- `partial`
- `failed`
- `blocked`
- `skipped`

Recommended `fulltext_source` values:

- `rss_reader_mcp`
- `rss_feed_content`
- `canonical_webpage`
- `publisher_article`
- `mirror`
- `unknown`

### Pipeline placement

```text
RSS fetch
-> URL exact dedup
-> domain-classifier
   - title clustering / same-event grouping
   - domain classification
   - fetch hints / priority
-> data/news_item_labels.jsonl
-> rss_reader_mcp fulltext fetch
-> data/news_item_fulltext.jsonl
-> later summary / clustering / briefing agents
```

### File responsibilities

- `data/news_item_labels.jsonl`: enriched article manifest used by `rss_reader_mcp`.
- `data/news_item_fulltext.jsonl`: fulltext-enriched article records for later summarization/aggregation agents.
- `src/news_feed_bootstrap/rss_reader_mcp.py`: Python-side MCP adapter that turns manifest rows into MCP calls.
- `src/news_feed_bootstrap/fulltext_fetcher.py`: orchestration layer that drives the fulltext stage.
- `scripts/agent_fetch_fulltext.py`: manual / agent entrypoint for fulltext extraction.

### Non-goals

`rss_reader_mcp` does **not**:

- summarize articles;
- write daily digests;
- assign categories;
- choose the final briefing articles;
- replace the domain-classifier stage.

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
- Direct MCP stdio smoke has worked against the active OPML: 155 OPML outlines, 155 MCP-listed feeds, and `latest --5` returned items.
- The local ignored `external/mcp-rss-aggregator` patch generates feed IDs from host + path/query + short URL hash, so same-domain feeds no longer overwrite each other in the MCP feed map.
- `external/` is gitignored. Do not commit it in this repo; preserve this patch later by upstreaming/forking or by adding an explicit setup patch step if MCP persistence is needed.
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

Output artifact contract additions:

- `data/active_feeds.json` stores active feed rows with `official_source: bool`.
- `data/news_items_raw.jsonl` stores raw item rows with `collector` and `official_source: bool`.
- `data/news_items_deduped.jsonl` stores downstream rows with top-level `collector`, top-level `official_source: bool`, and the original raw item under `raw`.
- `official_source: true` is only a conservative allowlist/provenance hint for downstream cross-source verification. It is **not** a full credibility score; unknown blogs, aggregators, community feeds, and vendor feeds remain `false` until reviewed.

Representative downstream row fields:

```json
{
  "id": "...",
  "title": "...",
  "url": "...",
  "normalized_url": "...",
  "feed_url": "...",
  "collector": "local_feedparser",
  "official_source": true,
  "raw": {
    "collector": "local_feedparser",
    "official_source": true
  }
}
```

## Important Files

| Path | Purpose |
| --- | --- |
| `configs/seed_sources.yaml` | Curated OPML/TXT seed sources; `enabled: false` keeps candidates without importing them. |
| `configs/official_sources.yaml` | Conservative allowlist used to mark `official_source` on active feeds and items. |
| `data/imported_feeds.json` | Imported feed candidates. |
| `data/imported_feeds.opml` | Imported feed candidates as OPML. |
| `data/feed_health.jsonl` | Feed health check results. |
| `data/active_feeds.json` | Active feed metadata, including `official_source`. |
| `data/active_feeds.opml` | OPML handoff file for RSS MCP servers. |
| `data/inactive_feeds.json` | Inactive or failed feed candidates plus health information. |
| `data/news_items_raw.jsonl` | Raw RSS item output, including `collector` and `official_source`. |
| `data/news_items_deduped.jsonl` | Main downstream model/agent input, including top-level `collector` and `official_source`. |
| `data/news_item_labels.jsonl` | Enriched article manifest with clustering, domain labels, and fulltext fetch hints. |
| `data/logs/mcp_config_hint.json` | Generated MCP config hint. |

Downstream agents should usually read:

```text
data/news_items_deduped.jsonl
```

Ranking and digest candidate agents should read both:

```text
data/news_items_deduped.jsonl
data/news_item_labels.jsonl
```

Rows include `collector`, currently `local_feedparser`, and `official_source`, currently derived from `configs/official_sources.yaml`. Future MCP integration should write `collector: "mcp:<server_id>"` while preserving `official_source` propagation.

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
