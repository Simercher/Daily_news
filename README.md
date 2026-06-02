# Daily_news

Daily_news is a Python news data layer MVP. It collects articles from configured providers, normalizes and stores article/event data, performs deterministic de-duplication and clustering/scoring steps, and exposes read access through a CLI and FastAPI app.

The Python distribution/project name in `pyproject.toml` is `Daily_news`. The command-line entry point is `daily-news`. The internal Python package namespace remains `news_system` for compatibility with the existing code layout.

## Current scope

This repository currently implements the news data layer only:

- collectors for RSS, NewsAPI, and GDELT inputs;
- SQLAlchemy models and repository helpers;
- Alembic migration scaffold for PostgreSQL;
- normalization, URL de-duplication, event clustering, scoring, and breaking-news detection;
- CLI jobs for collection and event display;
- FastAPI read endpoints for daily, breaking, and single-event views.

It does **not** include LLM summarization, Discord posting, a frontend, or a multi-agent orchestration layer.

## Setup

Requirements:

- Python 3.11+
- `uv`

Recommended development environment:

```bash
UV_PROJECT_ENVIRONMENT=.venv-news-system uv sync --dev
```

A conventional `.venv` is also fine if preferred:

```bash
UV_PROJECT_ENVIRONMENT=.venv uv sync --dev
```

Optional local environment configuration can be copied from `.env.example` if present.

## Tests

```bash
UV_PROJECT_ENVIRONMENT=.venv-news-system uv run pytest -q
```

## CLI

Show help:

```bash
UV_PROJECT_ENVIRONMENT=.venv-news-system uv run daily-news --help
```

Available commands:

```bash
UV_PROJECT_ENVIRONMENT=.venv-news-system uv run daily-news collect --source all --lookback-hours 1
UV_PROJECT_ENVIRONMENT=.venv-news-system uv run daily-news build-events
UV_PROJECT_ENVIRONMENT=.venv-news-system uv run daily-news watch-breaking
UV_PROJECT_ENVIRONMENT=.venv-news-system uv run daily-news show-daily
UV_PROJECT_ENVIRONMENT=.venv-news-system uv run daily-news show-breaking
```

## API

The FastAPI application is `news_system.api.main:app`.

Run it with:

```bash
UV_PROJECT_ENVIRONMENT=.venv-news-system uv run uvicorn news_system.api.main:app --reload
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
UV_PROJECT_ENVIRONMENT=.venv-news-system uv run alembic upgrade head
```

## Main directories

- `src/news_system/collectors/` — source collectors.
- `src/news_system/db/` — SQLAlchemy schema and database session setup.
- `src/news_system/storage/` — repository/storage helpers.
- `src/news_system/processors/` — normalization, de-duplication, clustering, scoring, and breaking detection logic.
- `src/news_system/jobs/` — CLI job orchestration.
- `src/news_system/api/` — FastAPI app.
- `tests/` — unit tests.
- `alembic/` — database migrations.
- `docs/` — human and agent-facing documentation.

## Notes

- Generated runtime data is not part of this repo's current source tree; old `data/` and `legacy/` directories have been removed.
- `uv.lock` may normalize the distribution name as `daily-news`; this is expected. Keep `pyproject.toml` as `name = "Daily_news"`.
- Keep references to the internal namespace `news_system` when discussing imports or source paths.
