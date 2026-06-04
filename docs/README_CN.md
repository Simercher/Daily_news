# Daily_news

Daily_news 是新聞摘要系統的資料與處理核心。這個 repository 內包含從設定來源收集文章、正規化並儲存文章與事件資料、執行確定性的去重、聚類、評分與 breaking-news 偵測，並透過 CLI 與 FastAPI app 提供讀取介面。

`pyproject.toml` 裡的 Python distribution/project 名稱是 `Daily_news`。命令列進入點是 `daily-news`。內部 Python package namespace 仍保留 `news_system`，以相容既有程式碼結構。

## 範圍與邊界

這個 repository 目前包含核心 pipeline 邏輯：

- RSS、NewsAPI、GDELT 輸入來源的 collectors；
- SQLAlchemy models 與 repository helpers；
- PostgreSQL 的 Alembic migration scaffold；
- 正規化、URL 去重、事件聚類、評分、breaking-news 偵測，以及 domain candidate 產生；
- 用於收集、事件建構與結構化候選輸出的 CLI jobs 與 repo-local helper scripts；
- Daily、breaking、單一事件檢視的 FastAPI read endpoints。

重要邊界如下：

- **repo 內程式碼**：確定性的收集、處理、儲存與結構化輸出。
- **repo 外的正式營運層**：Hermes profile、cron 排程、最終 LLM 推理、繁體中文摘要撰寫，以及 Discord forum 發送。

因此，這個 repository 本身沒有把 Hermes profile 或 cron scheduler 以 committed code 的方式放進來；但**目前實際上線的 production workflow 確實有包含 LLM 摘要與 Discord 發送**。

## 系統架構

```mermaid
flowchart LR
    subgraph Sources[外部新聞來源]
        RSS[RSS feeds]
        NewsAPI[NewsAPI]
        GDELT[GDELT]
    end

    subgraph Repo[Daily_news repository]
        Collect[Collectors + CLI 收集 jobs]
        DB[(PostgreSQL / SQLAlchemy)]
        Process[正規化 / 去重 / 聚類 / 評分]
        Break[Breaking-news 偵測]
        Domain[domain_summarizer.py\n結構化 JSON + rule_domain hints]
        API[FastAPI read API]
    end

    subgraph Ops[repo 外營運層]
        Hermes[Hermes profile: news-briefing-writer]
        Cron[Cron / Hermes cron scheduler]
        Discord[Discord forum + notification threads]
    end

    RSS --> Collect
    NewsAPI --> Collect
    GDELT --> Collect
    Cron --> Collect
    Collect --> DB
    DB --> Process
    Process --> Break
    Process --> Domain
    DB --> API
    Domain --> Hermes
    Break --> Hermes
    Cron --> Hermes
    Hermes --> Discord
```

## 正式營運 / Production pipeline

目前的 production system 是由本 repo 加上外部 Hermes 營運層共同組成。

### Daily-news flow

1. 以 `daily-news collect --lookback-hours 24` 收集文章（或由 operator/cron wrapper 包裝後執行）。
2. 以 `scripts/domain_summarizer.py --lookback-hours 24` 建立 domain candidate JSON。
3. 由外部 Hermes profile `news-briefing-writer` 進行最終 LLM 推理、動態挑選 domains、撰寫最終繁體中文摘要，並發送到 Discord。

目前應明確記錄的行為：

- `scripts/domain_summarizer.py` 現在預設會查詢 **lookback window 內所有非重複文章**。
- `--limit` 是可選的，只有顯式傳入時才會限制查詢數量。
- 這個 script 會輸出 structured JSON candidates 與 `rule_domain` hints。
- `rule_domain` 是確定性規則提供的參考值，**不是** production 中最後採用的 domain 決策。
- 最終 domain selection 由外部 Hermes profile 處理，而每個領域實際收錄的文章數量是**動態**的——通常約每個領域 4–10 則文章，而不是固定 5 則。

### Breaking-news flow

1. 以 `scripts/collect_rss_quick.py --lookback-hours 2` 執行快速 RSS-only collection。
2. 執行 `daily-news watch-breaking --lookback-minutes 120 --limit 10`。
3. 若存在 breaking events，營運層會發送到 Discord forum，並通知專用 notification thread；若沒有事件則保持安靜。

因此，這個 repository 應被理解為 daily 與 breaking news 的**處理引擎**，而 Hermes 負責最終推理、格式化與聊天室投遞。

## 端到端流程圖

```mermaid
flowchart TD
    Start([排程觸發]) --> Decide{流程類型}

    Decide -->|Daily news| D1[daily-news collect\n--lookback-hours 24]
    D1 --> D2[(Articles in PostgreSQL)]
    D2 --> D3[scripts/domain_summarizer.py\n--lookback-hours 24]
    D3 --> D4[Structured JSON candidates\n+ rule_domain hints]
    D4 --> D5[Hermes profile\nnews-briefing-writer]
    D5 --> D6[LLM 推理]
    D6 --> D7[動態每領域選材\n通常 4-10 則文章]
    D7 --> D8[繁體中文摘要]
    D8 --> D9[發送到 Discord forum]

    Decide -->|Breaking news| B1[scripts/collect_rss_quick.py\n--lookback-hours 2]
    B1 --> B2[daily-news watch-breaking\n--lookback-minutes 120 --limit 10]
    B2 --> B3{有 breaking events 嗎？}
    B3 -->|No| B4[保持安靜 / 不發送]
    B3 -->|Yes| B5[發送 breaking update 到 Discord forum]
    B5 --> B6[通知專用 Discord thread]
```

## 安裝

需求：

- Python 3.11+
- `uv`

建議的開發環境：

```bash
UV_PROJECT_ENVIRONMENT=.venv uv sync --dev
```

如果偏好一般 `.venv` 也可以：

```bash
UV_PROJECT_ENVIRONMENT=.venv uv sync --dev
```

如有 `.env.example`，可視需要複製成 local environment 設定。

## 測試

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run pytest -q
```

## CLI

顯示說明：

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news --help
```

可用指令：

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news collect --source all --lookback-hours 1
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news sources validate
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news sources list
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news build-events
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news watch-breaking
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news show-daily
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news show-breaking
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news db-smoke
```

`config/sources.yaml` 是 collection sources 的唯一入口。格式為 top-level `sources:` list，包含 `name`、`source_type`（`rss`、`newsapi`、`gdelt`）、`enabled`、URL/query metadata、trust/priority、country/category/language，以及可選的 `domain`、`base_url`、`params`。`daily-news collect --source all|rss|newsapi|gdelt|<name>` 會讀取此檔，且只收集 enabled sources。

RSS collection 會寫入設定的 SQLAlchemy database（`DATABASE_URL` / `SessionLocal`），正規化與 canonicalize URL、過濾早於 `--lookback-hours` 的文章、用唯一 `url_hash` upsert 去重、保存 `news_sources` 的 trusted/priority metadata、記錄 `collection_runs`，並輸出 JSON 統計（`fetched`、`inserted`、`duplicates`、各 source counts、errors）：

```bash
DATABASE_URL='postgresql+psycopg://daily_news:daily_news@localhost:5432/daily_news' \
  UV_PROJECT_ENVIRONMENT=.venv uv run daily-news collect --source rss --lookback-hours 24
```

如果 PostgreSQL 是跑在 host 而 CLI 在 container 內執行，`localhost` 可能指向 container 本身；請將 `DATABASE_URL` 改成可連到 host 的名稱/IP（例如環境支援時使用 `host.docker.internal`）。

## Scripts 與 operator 入口

目前 repo 內已提交的 `scripts/` 包含：

```bash
# 產生最近 24 小時的 structured domain candidates。
UV_PROJECT_ENVIRONMENT=.venv uv run python scripts/domain_summarizer.py --lookback-hours 24

# 提供 breaking monitoring 使用的快速 RSS-only collection。
UV_PROJECT_ENVIRONMENT=.venv uv run python scripts/collect_rss_quick.py --lookback-hours 2
```

Operator 備註：

- `scripts/domain_summarizer.py` 不負責 production 中最後的 LLM/domain 決策。
- 它的輸出是提供下游 Hermes automation 使用。
- Cron 排程與 Hermes profile 定義屬於 repo 外的營運議題，未提交在此處。
- 本文件刻意不記錄短期、聊天室專用的 Discord thread ID。

## API

FastAPI application 是 `news_system.api.main:app`。

啟動方式：

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run uvicorn news_system.api.main:app --reload
```

Endpoints：

- `GET /events/daily?date=YYYY-MM-DD&limit=10`
- `GET /events/breaking?since_minutes=180&limit=20`
- `GET /events/{event_id}`

## Database 與 Alembic

資料模型位於 `src/news_system/db/`。Alembic 設定在 `alembic.ini`，migrations 位於 `alembic/versions/`。

預設 Alembic URL：

```text
postgresql+psycopg://news:news@localhost:5432/news
```

確認目標 database 已存在且 connection string 正確後，可以套用 migrations：

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run alembic upgrade head
```

當 `DATABASE_URL` 指向已建立 Daily_news tables 的 PostgreSQL database 時，可執行可重用的 DB smoke check：

```bash
DATABASE_URL='postgresql+psycopg://daily_news:daily_news@localhost:5432/daily_news' \
  UV_PROJECT_ENVIRONMENT=.venv uv run daily-news db-smoke
```

它會檢查必要 tables、用 unique test values 寫入一筆 source/article/event/link/collection run，並輸出 JSON。

## 主要目錄

- `src/news_system/collectors/` — 來源 collectors。
- `src/news_system/db/` — SQLAlchemy schema 與 database session setup。
- `src/news_system/storage/` — repository/storage helpers。
- `src/news_system/processors/` — 正規化、去重、聚類、評分、breaking detection 與 domain summarizer 邏輯。
- `src/news_system/jobs/` — CLI job orchestration。
- `src/news_system/api/` — FastAPI app。
- `scripts/` — repo-local helper scripts，提供 candidate generation 與快速 collection。
- `tests/` — unit tests。
- `alembic/` — database migrations。
- `docs/` — 人類與 agent 使用的文件。

## 注意事項

- Generated runtime data 不屬於目前 source tree；舊的 `data/` 與 `legacy/` 目錄已移除。
- `uv.lock` 可能會把 distribution name normalization 成 `daily-news`；這是預期行為。`pyproject.toml` 請保持 `name = "Daily_news"`。
- 討論 imports 或 source paths 時，保留內部 namespace `news_system`。
- 描述能力時，請清楚區分 repo 內已提交的內容，以及 production Hermes workflow 在 repo 外增加的能力。
