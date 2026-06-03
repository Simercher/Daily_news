# Daily_news

Daily_news 是一個 Python 新聞資料層 MVP。它會從設定好的來源收集文章，正規化並儲存文章與事件資料，執行確定性的去重、聚類與評分流程，並透過 CLI 與 FastAPI app 提供讀取介面。

`pyproject.toml` 裡的 Python distribution/project 名稱是 `Daily_news`。命令列進入點是 `daily-news`。內部 Python package namespace 仍保留 `news_system`，以相容既有程式碼結構。

## 目前範圍

這個 repository 目前只實作新聞資料層：

- RSS、NewsAPI、GDELT 輸入來源的 collectors；
- SQLAlchemy models 與 repository helpers；
- PostgreSQL 的 Alembic migration scaffold；
- 正規化、URL 去重、事件聚類、評分與 breaking-news 偵測；
- 用於收集與事件顯示的 CLI jobs；
- Daily、breaking、單一事件檢視的 FastAPI read endpoints。

它目前**不**包含 LLM 摘要、Discord 發送、前端，或 multi-agent orchestration layer。

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
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news build-events
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news watch-breaking
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news show-daily
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news show-breaking
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news db-smoke
```

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
- `src/news_system/processors/` — 正規化、去重、聚類、評分與 breaking detection 邏輯。
- `src/news_system/jobs/` — CLI job orchestration。
- `src/news_system/api/` — FastAPI app。
- `tests/` — unit tests。
- `alembic/` — database migrations。
- `docs/` — 人類與 agent 使用的文件。

## 注意事項

- Generated runtime data 不屬於目前 source tree；舊的 `data/` 與 `legacy/` 目錄已移除。
- `uv.lock` 可能會把 distribution name normalization 成 `daily-news`；這是預期行為。`pyproject.toml` 請保持 `name = "Daily_news"`。
- 討論 imports 或 source paths 時，保留內部 namespace `news_system`。
