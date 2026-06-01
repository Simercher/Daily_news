# news_feed_bootstrap

`news_feed_bootstrap` 是一個小型自動化專案，用來把整理好的 RSS / OPML 清單轉成乾淨的 feed 與新聞資料檔。

它定位在後續模型流程之前的資料收集層。這個專案負責匯入 RSS feeds、檢查 feed 是否可用、抓取近期 RSS items，並輸出 JSON / JSONL。它不做摘要、不做分類、不做重要性排序、不做事件聚類、不呼叫 LLM API、不做 Discord 發送、不使用 Playwright，也不繞過 paywall 或存取限制。

## 如何理解這個專案

```text
curated RSS/OPML lists
-> imported feed candidates
-> minimum health check
-> active feeds JSON/OPML
-> raw RSS item fetch
-> deduped JSONL for downstream models
```

主要輸出：

- `data/active_feeds.json`
- `data/active_feeds.opml`
- `data/news_items_raw.jsonl`
- `data/news_items_deduped.jsonl`

## 安裝

在 repo 根目錄使用 `uv`：

```bash
uv sync
```

如果要跑開發工具與測試：

```bash
uv sync --dev
```

## 人類使用的 CLI

人類操作者可以使用 `news-feed` CLI：

```bash
uv run news-feed --help
uv run news-feed bootstrap
uv run news-feed fetch --mode local --since-hours 24
uv run news-feed dedup
uv run news-feed run-all --mode local --since-hours 24
```

`run-all` 會一次執行 bootstrap、local fetch 與 deduplication。

## Agent 入口

自動化 agent 應使用 `scripts/` 裡的 scripts。這些 scripts 的 stdout 只會輸出 JSON，logs 會寫到 `data/logs/`。

```bash
uv run python scripts/agent_status.py
uv run python scripts/agent_bootstrap.py
uv run python scripts/agent_run_daily.py --mode local --since-hours 24
```

完整 agent 交接說明請看 `docs/agent_handoff.md`。

## Seed Sources

Feed 來源設定在：

```text
configs/seed_sources.yaml
```

Seed URL 盡量使用直接的 OPML 或文字檔。GitHub pages 與 web directories 會先保留為註記，等 raw path 確認後再啟用。

目前包含的 seed families：

- `feedsForJournalists`
- `plenaryapp/awesome-rss-feeds`
- `awesome-tech-rss`
- `SecurityRSS`，目前列為需手動確認的來源

## MCP Handoff

這個 MVP 會替外部 RSS MCP servers 準備橋接檔：

```bash
uv run news-feed mcp-config --server imprvhub_mcp_rss_aggregator
```

產生的設定提示會寫到：

```text
data/logs/mcp_config_hint.json
```

MCP fetch 在這個 MVP 中只做到 adapter / handoff 階段。預設可運作路徑是 local mode。

## 測試

```bash
uv run pytest
uv run ruff check src scripts tests
```

## Legacy

舊版 source governance workflow 保留在 `legacy/old_governance/` 作為參考。它不屬於 MVP runtime path。
