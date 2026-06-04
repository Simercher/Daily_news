# Daily_news

Daily_news is the data and processing core for a news briefing system. Inside this repository, it collects articles from configured providers, normalizes and stores article/event data, performs deterministic de-duplication, clustering, scoring, and breaking-news detection, and exposes read access through a CLI and FastAPI app.

The Python distribution/project name in `pyproject.toml` is `Daily_news`. The command-line entry point is `daily-news`. The internal Python package namespace remains `news_system` for compatibility with the existing code layout.

## Scope and boundary

This repository contains the core pipeline logic:

- collectors for RSS, NewsAPI, and GDELT inputs;
- SQLAlchemy models and repository helpers;
- Alembic migration scaffold for PostgreSQL;
- normalization, URL de-duplication, event clustering, scoring, breaking-news detection, and domain candidate generation;
- CLI jobs and repo-local helper scripts for collection, event building, and structured candidate output;
- FastAPI read endpoints for daily, breaking, and single-event views.

Important boundary:

- **Repo-contained code**: deterministic collection/processing/storage and structured outputs.
- **Operational production layer outside this repo**: Hermes profile(s), cron scheduling, final LLM reasoning, Traditional Chinese briefing writing, and Discord forum posting.

So this repository alone does not ship the Hermes profile or cron scheduler as committed code, but the **active production workflow built around this repo does include LLM summarization and Discord posting**.

## System architecture

```mermaid
flowchart LR
    subgraph Sources[External news sources]
        RSS[RSS feeds]
        NewsAPI[NewsAPI]
        GDELT[GDELT]
    end

    subgraph Repo[Daily_news repository]
        Collect[Collectors + CLI collection jobs]
        DB[(PostgreSQL / SQLAlchemy)]
        Process[Normalization / dedupe / clustering / scoring]
        Break[Breaking-news detection]
        Domain[domain_summarizer.py\nstructured JSON + rule_domain hints]
        API[FastAPI read API]
    end

    subgraph Ops[Operational layer outside repo]
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

## Production / operational pipeline

The current production system is split across this repo and an external Hermes operational layer.

### Daily-news flow

1. Collect articles with `daily-news collect --lookback-hours 24` (or an operator/cron wrapper around it).
2. Build domain candidate JSON with `scripts/domain_summarizer.py --lookback-hours 24`.
3. The external Hermes profile `news-briefing-writer` performs final LLM reasoning, selects domains dynamically, writes the final Traditional Chinese summary, and posts to Discord.

Current behavior to document accurately:

- `scripts/domain_summarizer.py` now queries **all non-duplicate articles in the lookback window by default**.
- `--limit` is optional; it only constrains the query when explicitly passed.
- The script emits structured JSON candidates plus `rule_domain` hints.
- `rule_domain` is guidance from deterministic rules, **not** the final production domain decision.
- Final domain selection is handled by the external Hermes profile, and the number of selected items per domain is **dynamic** — typically about 4–10 articles per domain, not a fixed 5-item output.

### Breaking-news flow

1. Run fast RSS-only collection with `scripts/collect_rss_quick.py --lookback-hours 2`.
2. Run `daily-news watch-breaking --lookback-minutes 120 --limit 10`.
3. If breaking events exist, the operational layer posts to a Discord forum and notifies a dedicated notification thread; otherwise it stays silent.

The repository should therefore be read as the **processing engine** for both daily and breaking news, while Hermes handles the final reasoning, formatting, and chat delivery.

## End-to-end pipeline flow

```mermaid
flowchart TD
    Start([Scheduled run]) --> Decide{Flow type}

    Decide -->|Daily news| D1[daily-news collect\n--lookback-hours 24]
    D1 --> D2[(Articles in PostgreSQL)]
    D2 --> D3[scripts/domain_summarizer.py\n--lookback-hours 24]
    D3 --> D4[Structured JSON candidates\n+ rule_domain hints]
    D4 --> D5[Hermes profile\nnews-briefing-writer]
    D5 --> D6[LLM reasoning]
    D6 --> D7[Dynamic per-domain selection\nusually 4-10 articles]
    D7 --> D8[Traditional Chinese briefing]
    D8 --> D9[Post to Discord forum]

    Decide -->|Breaking news| B1[scripts/collect_rss_quick.py\n--lookback-hours 2]
    B1 --> B2[daily-news watch-breaking\n--lookback-minutes 120 --limit 10]
    B2 --> B3{Breaking events found?}
    B3 -->|No| B4[Silent / no post]
    B3 -->|Yes| B5[Post breaking update to Discord forum]
    B5 --> B6[Notify dedicated Discord thread]
```

## Setup

Requirements:

- Python 3.11+
- `uv`

Recommended development environment:

```bash
UV_PROJECT_ENVIRONMENT=.venv uv sync --dev
```

A conventional `.venv` is also fine if preferred:

```bash
UV_PROJECT_ENVIRONMENT=.venv uv sync --dev
```

Optional local environment configuration can be copied from `.env.example` if present.

## Tests

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run pytest -q
```

## CLI

Show help:

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news --help
```

Available commands:

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

`config/sources.yaml` is the single entry point for collection sources. It uses a top-level `sources:` list with `name`, `source_type` (`rss`, `newsapi`, `gdelt`), `enabled`, URL/query metadata, trust/priority, country/category/language, and optional `domain`, `base_url`, and `params`. `daily-news collect --source all|rss|newsapi|gdelt|<name>` loads this file and collects only enabled sources.

RSS collection writes to the configured SQLAlchemy database (`DATABASE_URL` / `SessionLocal`), normalizes/canonicalizes URLs, filters articles older than `--lookback-hours`, upserts by the unique `url_hash`, persists `news_sources` trust/priority metadata, records `collection_runs`, and prints JSON stats (`fetched`, `inserted`, `duplicates`, per-source counts, and errors):

```bash
DATABASE_URL='postgresql+psycopg://daily_news:daily_news@localhost:5432/daily_news' \
  UV_PROJECT_ENVIRONMENT=.venv uv run daily-news collect --source rss --lookback-hours 24
```

If PostgreSQL runs on the host from inside a container, `localhost` may point at the container rather than the host; set `DATABASE_URL` to the reachable host name/IP (for example `host.docker.internal` where supported).

## Scripts and operator entry points

Repo-local scripts currently committed in `scripts/` include:

```bash
# Build structured domain candidates from the last 24 hours.
UV_PROJECT_ENVIRONMENT=.venv uv run python scripts/domain_summarizer.py --lookback-hours 24

# Fast RSS-only collection for breaking monitoring.
UV_PROJECT_ENVIRONMENT=.venv uv run python scripts/collect_rss_quick.py --lookback-hours 2
```

Operator notes:

- `scripts/domain_summarizer.py` does not make the final production LLM/domain decision.
- Its output is intended for downstream Hermes automation.
- Cron scheduling and Hermes profile definitions are an external operational concern and are not committed here.
- This README intentionally does not document ephemeral Discord thread IDs.

## API

The FastAPI application is `news_system.api.main:app`.

Run it with:

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run uvicorn news_system.api.main:app --reload
```

Endpoints:

- `GET /events/daily?date=YYYY-MM-DD&limit=10`
- `GET /events/breaking?since_minutes=180&limit=20`
- `GET /events/{event_id}`

## Database and Alembic

The data model is defined under `src/news_system/db/`. Alembic configuration lives in `alembic.ini`, and migrations live under `alembic/versions/`.

The default Alembic URL is:

```text
postgresql+psycopg://news:news@localhost:5432/news
```

Apply migrations after ensuring the target database exists and the connection string is correct:

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run alembic upgrade head
```

When `DATABASE_URL` points at a PostgreSQL database with the Daily_news tables, run the reusable DB smoke check:

```bash
DATABASE_URL='postgresql+psycopg://daily_news:daily_news@localhost:5432/daily_news' \
  UV_PROJECT_ENVIRONMENT=.venv uv run daily-news db-smoke
```

It verifies the required tables, inserts one source/article/event/link/collection run using unique test values, and prints JSON.

## Main directories

- `src/news_system/collectors/` — source collectors.
- `src/news_system/db/` — SQLAlchemy schema and database session setup.
- `src/news_system/storage/` — repository/storage helpers.
- `src/news_system/processors/` — normalization, de-duplication, clustering, scoring, breaking detection, and domain summarizer logic.
- `src/news_system/jobs/` — CLI job orchestration.
- `src/news_system/api/` — FastAPI app.
- `scripts/` — repo-local helper scripts for candidate generation and fast collection.
- `tests/` — unit tests.
- `alembic/` — database migrations.
- `docs/` — human and agent-facing documentation.

## Notes

- Generated runtime data is not part of this repo's current source tree; old `data/` and `legacy/` directories have been removed.
- `uv.lock` may normalize the distribution name as `daily-news`; this is expected. Keep `pyproject.toml` as `name = "Daily_news"`.
- Keep references to the internal namespace `news_system` when discussing imports or source paths.
- When describing capabilities, distinguish clearly between what is committed in this repo and what the production Hermes workflow adds around it.
