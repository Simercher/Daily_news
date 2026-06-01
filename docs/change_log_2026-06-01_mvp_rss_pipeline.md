# 2026-06-01 MVP RSS Pipeline Change Log

這份文件記錄本次對 `Daily_news` 專案的修改。目標是讓新的 agent / 新 session 可以快速理解：原本狀態、修改內容、修改後成果、驗證方式與後續工作。

## 背景

使用者確認第一版方案可執行：

- 使用 GitHub curated RSS / OPML 清單取得 RSS source。
- 使用 RSS MCP 或 local feedparser 抓 RSS 內容。
- 第一版只輸出結構化資料，不做 LLM 摘要、Discord 發送、事件聚類或完整可信度評分。
- 保留 minimum health check 與 URL normalize / exact URL dedup。
- 每次修改都要留下文件，避免未來 session 壓縮時遺失決策脈絡。

## 修改前 baseline

### Repo

- Repo path: `/opt/data/plugins/Daily_news`
- Git branch: `main`
- Initial status: clean working tree before this change
- Initial test command: `uv run pytest -q`
- Initial test result: `8 passed in 0.70s`

### 原本主要行為

- `configs/seed_sources.yaml` 已包含：
  - feedsForJournalists OPML / TXT
  - plenaryapp awesome-rss-feeds US / UK
  - awesome-tech-rss
  - SecurityRSS repo page placeholder
- `SeedSource` model 沒有 `enabled` 欄位，因此 config 不能保留 disabled candidate。
- OPML importer 使用 strict XML parse：`defusedxml.ElementTree.fromstring()`。
  - 如果 OPML 中有未 escape 的 `&`，整個 seed source 會失敗。
- `agent_fetch_latest.py --mode mcp` 只會產生 MCP config hint，然後以 exit code 3 失敗。
- 沒有 `--mode auto`。
- `NewsItem` 沒有記錄 collector，因此後續看不出 item 是 local feedparser 還是 MCP 產生。

### 已實測的外部來源狀態

- `feedsForJournalists` OPML：HTTP 200，可 parse，約 129 feeds。
- `feedsForJournalists` TXT：HTTP 200，約 130 URL-like lines。
- `awesome-tech-rss`：HTTP 200，可 parse，約 143 feeds。
- `plenaryapp` US / UK OPML：HTTP 200，但 XML 不乾淨，strict parser 會失敗；regex 可抽出 US 約 10 feeds、UK 約 5 feeds。
- `SecurityRSS` raw OPML：`https://raw.githubusercontent.com/arch3rPro/SecurityRSS/master/SecurityRSS.opml`，HTTP 200，可 parse，約 378 feeds。
- `awesome_ML_AI_RSS_feed` default branch 是 `master`：
  - `https://raw.githubusercontent.com/vishalshar/awesome_ML_AI_RSS_feed/master/feed.opml` 可 parse，約 34 feeds。
  - `https://raw.githubusercontent.com/vishalshar/awesome_ML_AI_RSS_feed/master/rssowl.opml` 可 parse，約 41 feeds。
- `awesome-newsCN-feeds` default branch 是 `master`：
  - `https://raw.githubusercontent.com/RSS-Renaissance/awesome-newsCN-feeds/master/feedlist.opml` 可 parse，約 15 feeds。

## 本次預定修改

1. `SeedSource` 新增 `enabled: bool = True`，讓 config 能保留 disabled candidate。
2. 更新 `configs/seed_sources.yaml`：
   - 第一版啟用 feedsForJournalists、awesome-tech-rss、plenaryapp US/UK。
   - SecurityRSS、awesome_ML_AI_RSS_feed、awesome-newsCN-feeds 先保留但 disabled。
3. `opml_importer.py` 新增 tolerant OPML fallback：
   - strict XML parse 失敗時，用 regex 抽 `xmlUrl` / `htmlUrl` / `title` / `text`。
4. `NewsItem` 與 fetch/dedup output 補 `collector` 欄位。
5. 新增 `agent_fetch_latest.py --mode auto`：
   - 第一版 MCP 尚未實作時，auto mode 產生 MCP config hint 並 fallback local feedparser。
6. 更新 docs，讓新 agent 讀文件即可知道第一版實際入口與限制。
7. 執行測試與 agent command 驗證。

## 修改紀錄

> 後續每個修改都要補在這裡，格式：原本是什麼 → 修改什麼 → 成果是什麼 → 驗證方式。

### 2026-06-01 follow-up completion

1. `SeedSource.enabled`
   - 原本：`SeedSource` 無法保留 disabled candidate。
   - 修改：`src/news_feed_bootstrap/models.py` 新增 `enabled: bool = True`。
   - 成果：`configs/seed_sources.yaml` 可保留 SecurityRSS、AI/ML、中文來源等 disabled candidate，第一版 bootstrap 只匯入 enabled sources。
   - 驗證：`uv run pytest -q`，含 `test_seed_source_can_be_disabled`。

2. curated seed source config
   - 原本：config 混有第一版要啟用的來源與尚未確認的候選來源，無 enabled gate。
   - 修改：`configs/seed_sources.yaml` 啟用 feedsForJournalists OPML、plenaryapp US/UK、awesome-tech-rss；保留 feedsForJournalists TXT、SecurityRSS、awesome_ML_AI_RSS_feed、awesome-newsCN-feeds 但 `enabled: false`。
   - 成果：實測 bootstrap 匯入 282 個 feed candidates。
   - 驗證：`NEWS_FEED_TIMEOUT_SECONDS=3 uv run python scripts/agent_run_daily.py --mode auto --server imprvhub_mcp_rss_aggregator --since-hours 24 --force-bootstrap` 成功，stdout stats `imported_feeds: 282`。

3. tolerant OPML fallback
   - 原本：未 escape `&` 會讓 strict XML parser 直接失敗。
   - 修改：`opml_importer.py` strict parse 失敗時 fallback 到 regex-based outline attribute extraction，抽 `xmlUrl` / `htmlUrl` / `title` / `text`。
   - 成果：plenaryapp US/UK 這類 malformed OPML 可匯入，不會中斷整批 seed import。
   - 驗證：`test_import_opml_falls_back_when_xml_contains_unescaped_ampersand` 通過；forced bootstrap 成功。

4. collector 欄位
   - 原本：raw/deduped item 看不出是 local feedparser 還是 MCP collector 產生。
   - 修改：`NewsItem.collector` 預設 `local_feedparser`；fetcher 與 downstream row 會保留 collector。
   - 成果：`data/news_items_raw.jsonl` 與 `data/news_items_deduped.jsonl` 都包含 collector；目前實測 collectors 為 `local_feedparser`。
   - 驗證：`test_downstream_item_keeps_collector`、`test_fetch_feed_items_records_published_fallback` 通過；artifact inspection 顯示 raw/dedup collectors 都是 `local_feedparser`。

5. MCP/auto mode behavior
   - 原本：`--mode mcp` 只產生 hint 並 exit 3；沒有 `--mode auto`。
   - 修改：`agent_fetch_latest.py` / `agent_run_daily.py` 支援 `--mode auto`，會產生 `data/logs/mcp_config_hint.json` 並 fallback local feedparser；`--mode mcp` 保持 expected failure with exit code 3。
   - 成果：Hermes automation 可用 `--mode auto` 當預設入口；MCP hint 保留給未來真正 stdio MCP client 或外部 MCP tool。
   - 驗證：`agent_generate_mcp_config.py` 成功；`agent_fetch_latest.py --mode mcp ...` stdout `ok: false` 且 exit code `3`；`agent_run_daily.py --mode auto ...` 成功。

6. runtime timeout control
   - 原本：external RSS request timeout 固定 15 秒；forced end-to-end validation 可能被少數慢 host 拖到超過 automation timeout。
   - 修改：`src/news_feed_bootstrap/utils.py` 允許用 `NEWS_FEED_TIMEOUT_SECONDS` 覆蓋 timeout，預設仍為 15 秒。
   - 成果：保留 production completeness 的預設值，同時可用短 timeout 完成端到端 validation。
   - 驗證：先新增 `test_timeout_can_be_configured_with_environment` 並看見失敗（`15 != 3.0`），再實作後通過；forced pipeline validation 使用 `NEWS_FEED_TIMEOUT_SECONDS=3` 成功。

7. packaging metadata cleanup
   - 原本：`pyproject.toml` 指向不存在的 `README_EN.md`，`uv build` 會出現 setuptools warning。
   - 修改：`readme = "README.md"`。
   - 成果：package metadata 指向實際存在的 README。
   - 驗證：修改前 `uv build` 成功但警告 README_EN.md missing；修改後納入 final verification。

8. docs 收尾
   - 原本：handoff docs 已描述 auto/MCP fallback，但未記錄 timeout override 與本次實測結果。
   - 修改：更新 `README.md`、`docs/README_CN.md`、`docs/agent_handoff.md`、`docs/hermes_agent_workflow.md`；本 change log 補完整修改與驗證紀錄。
   - 成果：新 session 讀文件即可知道 enabled seed gate、tolerant OPML、collector、auto mode、timeout override、MCP MVP 限制與驗證命令。
   - 驗證：final docs are plain markdown; code validation 見下方。

## 驗證紀錄

### Automated tests / lint

```text
$ env -u VIRTUAL_ENV uv run pytest -q
15 passed in 0.26s

$ env -u VIRTUAL_ENV uv run ruff check src scripts tests
All checks passed!

$ env -u VIRTUAL_ENV uv build
Successfully built dist/news_feed_bootstrap-0.1.0.tar.gz
Successfully built dist/news_feed_bootstrap-0.1.0-py3-none-any.whl
```

### MCP expected-failure path

```text
$ env -u VIRTUAL_ENV uv run python scripts/agent_fetch_latest.py --mode mcp --server imprvhub_mcp_rss_aggregator --since-hours 24
{
  "ok": false,
  "command": "agent_fetch_latest",
  "message": "MCP fetch is not implemented in this MVP.",
  "error": {
    "type": "ExternalServiceError",
    "detail": "Generated data/logs/mcp_config_hint.json. Hermes may call the RSS MCP tool externally or fallback to local mode."
  },
  "outputs": {},
  "stats": {},
  "warnings": ["Fallback to local mode is available."]
}
MCP_EXIT_CODE=3
```

### End-to-end forced auto pipeline

```text
$ env -u VIRTUAL_ENV NEWS_FEED_TIMEOUT_SECONDS=3 uv run python scripts/agent_run_daily.py --mode auto --server imprvhub_mcp_rss_aggregator --since-hours 24 --force-bootstrap
{
  "ok": true,
  "command": "agent_run_daily",
  "message": "Daily RSS pipeline completed.",
  "stats": {
    "imported_feeds": 282,
    "active_feeds": 148,
    "inactive_feeds": 134,
    "raw_items": 824,
    "deduped_items": 738
  },
  "warnings": ["MCP fetch is not implemented in this MVP; generated config hint and used local feedparser fallback."]
}
```

Artifact inspection after the run:

```text
data/imported_feeds.json: exists=True size=144726
data/imported_feeds.opml: exists=True size=36266
data/feed_health.jsonl: exists=True size=135746
data/active_feeds.json: exists=True size=79492
data/active_feeds.opml: exists=True size=19681
data/inactive_feeds.json: exists=True size=152125
data/news_items_raw.jsonl: exists=True size=1497627
data/news_items_deduped.jsonl: exists=True size=2775162
data/logs/mcp_config_hint.json: exists=True size=579
COUNTS {'raw': 824, 'deduped': 738}
RAW_COLLECTORS ['local_feedparser']
DEDUP_COLLECTORS ['local_feedparser']
MCP_HINT_KEYS ['capabilities', 'mcp_config', 'recommended', 'repo', 'server_id']
```

### 2026-06-01 docs dedup pass

- 原本：`README.md` / `docs/README_CN.md` 偏向概略介紹，沒有明確分清「目前能做」與「還不能做」；`docs/agent_handoff.md` 和 `docs/hermes_agent_workflow.md` 都重複列出 pipeline、MCP fallback、run commands，未來容易 drift。
- 修改：
  - `README.md` 和 `docs/README_CN.md` 改成給人看的狀態說明，明確列出 MVP capabilities、not implemented yet、pipeline shape、quick run、seed source、MCP handoff。
  - `docs/agent_handoff.md` 改成唯一 canonical agent runbook，集中放 runtime contract、pipeline、commands、MCP modes、JSON contract、file map、validation、troubleshooting。
  - `docs/hermes_agent_workflow.md` 改成短版 Hermes overlay，只保留 Hermes 預設入口、validation command、decision rules，並明確要求不要重複 general runbook content。
- 成果：給人看的 README 與給 agent 的 runbook 分工明確；agent 文件只剩一個 source of truth，Hermes 檔案只補 Hermes-specific routing。
- 驗證：`git diff --check`、`uv run pytest -q`、`uv run ruff check src scripts tests`。

### 2026-06-01 Hermes MCP config and final validation pass

- 原本：MVP 只產生 `data/logs/mcp_config_hint.json`，文件也只把 MCP 視為 future handoff；`imprvhub/mcp-rss-aggregator` 尚未在 Hermes native MCP config 中完成實測。
- 修改：將 `imprvhub/mcp-rss-aggregator` clone/build 到 ignored `external/mcp-rss-aggregator/`，修正 external repo 的 MCP SDK capabilities typing、`FEEDS_PATH` env 讀取、sample OPML 檔名，並讓 `/opt/data/config.yaml` 的 `mcp_servers.rssAggregator` 指向 build artifact 與 `data/active_feeds.opml`。
- 成果：`hermes mcp test rssAggregator` 可連線並 discovery 到一個 `rss` tool；Daily_news Python pipeline 仍維持 MVP 行為，不直接呼叫 MCP tool，`--mode auto` 會產生 hint 後使用 local feedparser fallback。
- 驗證：

```text
$ hermes mcp test rssAggregator
Testing 'rssAggregator'...
  Transport: stdio → node
  Auth: none
  ✓ Connected (540ms)
  ✓ Tools discovered: 1

    rss  Interfaz principal para Hacker News con comandos simpli...

$ env -u VIRTUAL_ENV uv run pytest -q
15 passed in 0.29s

$ env -u VIRTUAL_ENV uv run ruff check src scripts tests
All checks passed!

$ git -c safe.directory=/opt/data/plugins/Daily_news diff --check
# no output

$ env -u VIRTUAL_ENV uv build
Successfully built dist/news_feed_bootstrap-0.1.0.tar.gz
Successfully built dist/news_feed_bootstrap-0.1.0-py3-none-any.whl

$ env -u VIRTUAL_ENV NEWS_FEED_TIMEOUT_SECONDS=3 uv run python scripts/agent_run_daily.py --mode auto --server imprvhub_mcp_rss_aggregator --since-hours 24 --force-bootstrap
{
  "ok": true,
  "command": "agent_run_daily",
  "message": "Daily RSS pipeline completed.",
  "stats": {
    "imported_feeds": 282,
    "active_feeds": 153,
    "inactive_feeds": 129,
    "raw_items": 851,
    "deduped_items": 749
  },
  "warnings": [
    "MCP fetch is not implemented in this MVP; generated config hint and used local feedparser fallback."
  ]
}
```

Artifact inspection after this run:

```text
data/imported_feeds.json: feeds=282 size=144726
data/active_feeds.json: feeds=153 size=82045
data/inactive_feeds.json: feeds=129 size=146521
data/feed_health.jsonl: lines=282 size=135884
data/news_items_raw.jsonl: lines=851 size=1552647 collectors=['local_feedparser']
data/news_items_deduped.jsonl: lines=749 size=2848691 collectors=['local_feedparser']
data/logs/mcp_config_hint.json: keys=['capabilities', 'mcp_config', 'recommended', 'repo', 'server_id'] size=579
```

## 後續工作

- 真正接上 RSS MCP stdio/client 後，讓 `collector` 使用 `mcp:<server_id>`，並新增 MCP output normalization tests。
- 若要做 production-grade crawl，可考慮 parallel fetch/health check、per-host rate limiting、retry/backoff 與更完整的 feed quality scoring。
- 下游 LLM 摘要、Discord forum 發送、事件聚類、可信度評分仍不屬於這個 MVP runtime path。
