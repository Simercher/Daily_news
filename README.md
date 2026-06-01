# news_feed_bootstrap

`news_feed_bootstrap` 是 Daily News 的 RSS 收集與前處理層。它會把 curated RSS / OPML seed 清單轉成可用的 active feed 檔案，抓取近期 RSS items，並把可供下游 agent 使用的 JSONL 準備好。

這個 repo 目前**不是完整每日新聞簡報 bot**。它負責準備後續分類、聚類、摘要、排序與 Discord 發送所需的原始資料。

## 這個 MVP 能做什麼

目前 pipeline 可以：

1. 從 `configs/seed_sources.yaml` 匯入 curated RSS / OPML seed lists。
2. 用 `enabled: false` 在 config 裡保留未來候選 source。
3. 解析正常 OPML；如果 OPML 有未 escape 的 `&` 等 XML 問題，會 fallback 到 tolerant outline attribute extraction。
4. 做最低限度 RSS feed health check。
5. 匯出 active feeds 的 JSON 與 OPML。
6. 使用 local `feedparser` 抓取近期 RSS items。
7. 用 normalized exact URL 做 deduplication。
8. 保留 `collector` 欄位，讓下游知道 item 來自 local feedparser，或未來的 MCP collector。
9. 用保守 allowlist 標記 `official_source`，方便下游做 cross-source verification。
10. 產生 RSS MCP config hint file，供未來或外部 MCP handoff 使用。
11. 提供 agent-friendly scripts，stdout 最後會輸出一個 JSON object。

## 目前不做的事

這個 MVP 目前**不會**：

- 透過真正的 MCP stdio client 抓 RSS；
- 用 LLM 摘要文章；
- 分類成最終每日新聞類別；
- 做重要性排序或可信度評分；
- 語意聚類文章為事件；
- 抓取 RSS 以外的全文；
- 繞過 paywall、CAPTCHA 或存取限制；
- 發送到 Discord。

## Pipeline 形狀

```text
configs/seed_sources.yaml
-> 匯入 enabled curated OPML/TXT feed lists
-> tolerant OPML parsing（strict XML 失敗時）
-> data/imported_feeds.json / data/imported_feeds.opml
-> minimum feed health check
-> data/active_feeds.json / data/active_feeds.opml
-> 從 configs/official_sources.yaml 標記 conservative official_source
-> local RSS item fetch，或 auto mode MCP hint + local fallback
-> data/news_items_raw.jsonl
-> normalized exact-URL deduplication
-> data/news_items_deduped.jsonl
-> domain-classifier semantic labeling + title clustering
-> data/news_item_labels.jsonl
```

### 主要輸出

- `data/active_feeds.json`
- `data/active_feeds.opml`
- `data/news_items_raw.jsonl`
- `data/news_items_deduped.jsonl`
- `data/news_item_labels.jsonl`
- `data/logs/mcp_config_hint.json`

### 下游通常讀哪個檔案

- 一般下游：`data/news_items_deduped.jsonl`
- 分析 / 分類 / 排序 / 全文抓取下游：`data/news_items_deduped.jsonl` + `data/news_item_labels.jsonl`

## 安裝

在 repo 根目錄使用 `uv`：

```bash
uv sync
```

如果要跑開發工具與測試：

```bash
uv sync --dev
```

## 快速執行

MVP one-shot run：

```bash
uv run python scripts/agent_run_daily.py --mode auto --since-hours 24
```

`--mode auto` 目前會產生 MCP config hint，然後因為這個 MVP 尚未實作真正 MCP fetch，所以 fallback 到 local feedparser。

強制重新 bootstrap，並讓驗證 run 不被慢 RSS host 拖太久：

```bash
NEWS_FEED_TIMEOUT_SECONDS=3 uv run python scripts/agent_run_daily.py --mode auto --since-hours 24 --force-bootstrap
```

`NEWS_FEED_TIMEOUT_SECONDS` 預設是 `15`。端到端驗證時可以設短一點；如果正式收集比較重視完整性，就用預設值或設更高秒數。

## 人類使用的 CLI

人類操作者也可以使用 `news-feed` CLI：

```bash
uv run news-feed --help
uv run news-feed bootstrap
uv run news-feed fetch --mode local --since-hours 24
uv run news-feed dedup
uv run news-feed run-all --mode local --since-hours 24
```

Agent 應優先使用 `scripts/agent_*.py`，因為 script stdout 是 machine-readable JSON。

## Agent 文件

Agent 的 canonical runbook 是：

```text
docs/agent_handoff.md
```

Hermes 專用補充刻意保持簡短，避免重複維護，放在：

```text
docs/hermes_agent_workflow.md
```

## Seed Sources

Feed 來源設定在：

```text
configs/seed_sources.yaml
```

目前啟用的 source families：

- `feedsForJournalists` OPML
- `plenaryapp/awesome-rss-feeds` United States / United Kingdom
- `awesome-tech-rss`

目前保留但 disabled 的候選來源：

- `feedsForJournalists` text list，主要作為重疊 fallback
- `SecurityRSS`，未來資安專區可用
- `awesome_ML_AI_RSS_feed`，未來 AI / ML specialist run 可用
- `awesome-newsCN-feeds`，中文第三方或 generated feeds 需要額外檢查

`enabled: false` 的來源會保留在設定檔中，但不會被 bootstrap 匯入。

## Official Source Marker

`configs/official_sources.yaml` 是 first-party / recognized publisher source 的保守 allowlist。Pipeline 會把 `official_source` 寫入：

- `data/active_feeds.json`
- `data/news_items_raw.jsonl`
- `data/news_items_deduped.jsonl`

`official_source: true` 是給下游 cross-source verification 用的提示，不是完整可信度評分。未知 blog、aggregator、community feeds、vendor blogs 預設保持 `false`，直到明確 review 後加入 allowlist。

## MCP Handoff

產生 MCP config hint：

```bash
uv run python scripts/agent_generate_mcp_config.py --server imprvhub_mcp_rss_aggregator
```

產生的 hint 會寫到：

```text
data/logs/mcp_config_hint.json
```

MVP 的 expected behavior：

- `--mode auto`：寫入 MCP hint，然後 fallback 到 local feedparser。
- `--mode local`：只使用 local feedparser。
- `--mode mcp`：寫入 MCP hint，並保留 MCP-first 的行為定義；目前若真正 MCP fetch 還沒接好，仍可 fallback local。

目前環境的 Hermes native MCP 狀態：

- `/opt/data/config.yaml` 已有 `mcp_servers.rssAggregator`，指向 `external/mcp-rss-aggregator/build/index.js`，並用 `FEEDS_PATH=data/active_feeds.opml`。
- `hermes mcp test rssAggregator` 可以連線，並 discovery 到一個 `rss` tool。
- 目前 local `external/mcp-rss-aggregator` patch 會用 host + path/query + URL 短 hash 產生 feed ID，因此同 domain 多個 feeds 不會互相覆蓋。
- `external/` 已被 gitignore；這一步不要 commit 或 fork。若之後需要長期保存 MCP patch，再用 upstream/fork 或明確 setup patch 方式處理。
- Daily_news Python pipeline 目前仍不會直接呼叫這個 MCP tool；在加入 stdio MCP client / output normalizer 前，`--mode auto` 仍會使用 local feedparser fallback，並在 items 裡保留 `collector: "local_feedparser"`。

## 測試

```bash
uv run pytest -q
uv run ruff check src scripts tests
uv build
```

## Legacy

舊版 source governance workflow 保留在 `legacy/old_governance/` 作為參考。它不屬於 MVP runtime path。
