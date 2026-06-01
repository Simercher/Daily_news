# news_feed_bootstrap

`news_feed_bootstrap` 是一個輕量級的 RSS bootstrap 層，用來收集每日新聞來源。

MVP 流程如下：

```text
GitHub curated RSS/OPML lists
-> 匯入 feed_url 候選清單
-> minimum health check
-> data/active_feeds.opml 與 data/active_feeds.json
-> 使用本地 feedparser 抓取，或交給外部 RSS MCP server
-> data/news_items_raw.jsonl
-> 後續模型負責去重、分類、重要性判斷與摘要
```

本專案刻意不執行 LLM 呼叫、不做 Discord bot、不使用 Playwright、不從首頁 discovery feed、不做來源可信度評分、不繞過 paywall、login wall、Cloudflare 或 captcha。

## 安裝

```bash
cd /Users/linyuzhan/Documents/.data/daily_news
export UV_CACHE_DIR=.uv-cache
export UV_PYTHON_INSTALL_DIR=.uv-python
uv sync
uv sync --dev
```

快速檢查：

```bash
uv run news-feed --help
uv run python -m news_feed_bootstrap.cli --help
uv run python scripts/agent_run_daily.py --mode local --since-hours 24
```

## 設定 Seed Sources

編輯 `configs/seed_sources.yaml`。

Seed URL 盡量使用直接的 `raw.githubusercontent.com` OPML 或文字檔。GitHub pages 與 web directories 會先保留為註記，等 raw path 手動確認後再啟用。

目前包含的 seeds：

- `feedsForJournalists`：OPML 與文字清單，高優先級。
- `plenaryapp/awesome-rss-feeds`：美國與英國 OPML 範例，中高優先級。
- `awesome-tech-rss`：科技、AI、startup、engineering OPML，中優先級。
- `SecurityRSS`：因 raw feed list path 尚未固定，目前列為需手動確認的來源。

## Bootstrap Feeds

```bash
uv run news-feed bootstrap
```

這會把 seed sources 匯入 `data/imported_feeds.json`，執行 minimum health check，並輸出：

- `data/feed_health.jsonl`
- `data/active_feeds.json`
- `data/active_feeds.opml`

只有 active、可解析，且近期有更新的 feeds 會被寫入 active outputs。

也可以分步執行：

```bash
uv run news-feed bootstrap-seeds
uv run news-feed health-check
```

## Local Fetch Mode

Local mode 不會啟動 MCP。它直接使用 `feedparser`，適合作為測試與 fallback 路徑：

```bash
uv run news-feed fetch --mode local --since-hours 24
uv run news-feed dedup
```

輸出：

- `data/news_items_raw.jsonl`

這份輸出是原始 RSS item data。後續模型階段應負責分類、重要性判斷、事件聚類與摘要。

## MCP Mode

第一版提供 MCP adapter abstraction，並輸出 `data/active_feeds.opml` 給外部 RSS MCP servers 使用。

```bash
uv run news-feed mcp-notes
```

候選 MCP servers：

- `rss-reader-mcp`：RSS aggregation 與 article content extraction。
- `buhe/mcp_rss`：OPML import 與長期儲存；需要 MySQL。
- `imprvhub/mcp-rss-aggregator`：OPML import、category filtering、latest articles。
- `veithly/rss-mcp`：通用 RSS/Atom parser 與 RSSHub-compatible feeds。

stdio MCP client 會等目標 RSS MCP server 選定後再實作，目前刻意保留為 TODO。

## Hermes Agent 使用方式

Hermes agent 應使用 `scripts/agent_*.py`。人類操作者可以使用 `news-feed` CLI。

Agent stdout 只會輸出 JSON。Logs 會寫入 `data/logs/`。

```bash
uv run python scripts/agent_status.py
uv run python scripts/agent_bootstrap.py
uv run python scripts/agent_generate_mcp_config.py --server imprvhub_mcp_rss_aggregator
uv run python scripts/agent_fetch_latest.py --mode local --since-hours 24
uv run python scripts/agent_dedup.py
uv run python scripts/agent_run_daily.py --mode local --since-hours 24
```

Daily run 會在 `data/active_feeds.json` 或 `data/active_feeds.opml` 不存在，或超過 24 小時未更新時自動 bootstrap。

標準 Hermes workflow 與 JSON contract 請見 `docs/hermes_agent_workflow.md`。

## Legacy

舊版 source governance workflow 已移到 `legacy/old_governance/`。其中包含先前的 homepage discovery、`source_score` / `feed_score`、`approved_feeds.yaml`、article extraction 與相關 tests。這些內容只作為參考保留，不屬於 MVP CLI 主流程。
