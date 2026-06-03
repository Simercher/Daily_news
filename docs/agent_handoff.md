# Daily_news Agent Handoff

This document is the handoff/runbook for an automation agent that needs to work on or operate the Daily_news repository.

## Project purpose

Daily_news is a Python news data layer MVP. It collects candidate news articles, normalizes and stores articles/events, deduplicates and clusters related items, scores events, marks breaking events, and exposes read access through a CLI and FastAPI application.

The Python project name must remain `Daily_news` in `pyproject.toml`. The command-line entry point is `daily-news`. The internal Python package namespace is `news_system`; keep that namespace in imports and source-path references.

## Current scope

In scope now:

- RSS, NewsAPI, and GDELT collection interfaces.
- SQLAlchemy database models and repository helpers.
- Alembic migration scaffold for PostgreSQL.
- Article normalization.
- Deterministic URL-based de-duplication.
- Event clustering, scoring, and breaking-event detection.
- CLI jobs for collection and event views.
- FastAPI read endpoints.

Out of scope now:

- LLM summarization or ranking by an LLM.
- Discord posting.
- Frontend/UI.
- Multi-agent orchestration.
- Paywall/CAPTCHA bypassing or restricted-content access.

## Environment setup

Run commands from the repository root:

```bash
cd /opt/data/plugins/Daily_news
```

Requirements:

- Python 3.11+
- `uv`

Recommended environment command:

```bash
UV_PROJECT_ENVIRONMENT=.venv uv sync --dev
```

A standard `.venv` can also be used if the caller prefers:

```bash
UV_PROJECT_ENVIRONMENT=.venv uv sync --dev
```

Notes:

- - `uv.lock` may normalize the package name to `daily-news`; that is acceptable. `pyproject.toml` must keep `name = "Daily_news"`.

## Verification and tests

Primary test command:

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run pytest -q
```

CLI smoke test:

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news --help
```

Directory cleanup check:

```bash
test ! -d data && test ! -d legacy
```

If a dependency or interpreter is missing, repair the uv environment first and rerun the command. Do not infer success without real command output.

## CLI

Entrypoint:

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run daily-news --help
```

Current subcommands:

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

Current CLI output is compact JSON for job results. `config/sources.yaml` is the single source configuration entry point; `sources validate/list` check and show the normalized source schema, and `collect` only builds collectors for enabled config entries.

RSS collection path to verify Step 3:

```bash
DATABASE_URL='postgresql+psycopg://daily_news:daily_news@localhost:5432/daily_news' \
  UV_PROJECT_ENVIRONMENT=.venv uv run daily-news collect --source rss --lookback-hours 24
```

Expected JSON includes top-level `fetched`, `inserted`, `duplicates`, `filtered_old`, `source_counts`, and `errors`. Collection uses `DATABASE_URL`/`SessionLocal`, writes `news_sources` metadata (`trusted`, `priority`, etc.), records `collection_runs`, normalizes/canonicalizes URLs, and upserts by unique `url_hash`. The current no-explicit-session CLI path calls `Base.metadata.create_all(engine)` before opening a session; this is convenient for SQLite/dev smoke runs but production PostgreSQL should still be managed with Alembic migrations and an explicitly verified `DATABASE_URL`/schema. If running inside a container, do not assume PostgreSQL on the host is reachable at `localhost`; set `DATABASE_URL` to the actual reachable host/IP.

For PostgreSQL verification, set `DATABASE_URL` explicitly and run `daily-news db-smoke`. The smoke command verifies required tables and inserts a unique source/article/event/link/collection run. `tests/test_postgres_integration.py` calls the same function and skips unless `DATABASE_URL` is present.


## Cron/Hermes wrappers

Use the repository-local wrappers for scheduling rather than embedding long `uv run daily-news ...` commands in cron. They are POSIX `sh` scripts, executable, safe to invoke from any current working directory, and resolve the repo root from their own location.

Dedicated Hermes cron mounting/scheduling details live in [`docs/hermes_cron.md`](hermes_cron.md); keep this section as a summary and do not duplicate that full runbook here.

Common behavior:

- preserve caller-provided `DATABASE_URL`, API keys, and other environment values;
- optionally load `/opt/data/plugins/Daily_news/.env` for variables that are not already set;
- default `UV_PROJECT_ENVIRONMENT=.venv` unless the caller sets another value;
- run the CLI through `uv run daily-news` from the repository root.

Commands:

```bash
# Defaults: NEWS_SOURCE/all and LOOKBACK_HOURS/1.
/opt/data/plugins/Daily_news/scripts/cron_collect.sh
/opt/data/plugins/Daily_news/scripts/cron_collect.sh rss 24
NEWS_SOURCE=gdelt LOOKBACK_HOURS=6 /opt/data/plugins/Daily_news/scripts/cron_collect.sh

# Defaults: LOOKBACK_HOURS/24 and LIMIT/10.
/opt/data/plugins/Daily_news/scripts/cron_build_daily_events.sh
/opt/data/plugins/Daily_news/scripts/cron_build_daily_events.sh 48 20
LOOKBACK_HOURS=48 LIMIT=20 /opt/data/plugins/Daily_news/scripts/cron_build_daily_events.sh

# Default: LOOKBACK_MINUTES/60.
/opt/data/plugins/Daily_news/scripts/cron_watch_breaking.sh
/opt/data/plugins/Daily_news/scripts/cron_watch_breaking.sh 180
LOOKBACK_MINUTES=180 /opt/data/plugins/Daily_news/scripts/cron_watch_breaking.sh
```

Hermes cron example command entries, assuming PostgreSQL is already provisioned and reachable:

```bash
DATABASE_URL='postgresql+psycopg://daily_news:daily_news@localhost:5432/daily_news' /opt/data/plugins/Daily_news/scripts/cron_collect.sh
DATABASE_URL='postgresql+psycopg://daily_news:daily_news@localhost:5432/daily_news' /opt/data/plugins/Daily_news/scripts/cron_build_daily_events.sh
DATABASE_URL='postgresql+psycopg://daily_news:daily_news@localhost:5432/daily_news' /opt/data/plugins/Daily_news/scripts/cron_watch_breaking.sh
```

Do not claim these jobs are installed unless a separate scheduler/Hermes cron action actually creates them.

## API

FastAPI app object:

```text
news_system.api.main:app
```

Run locally:

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run uvicorn news_system.api.main:app --reload
```

Endpoints:

- `GET /events/daily?date=YYYY-MM-DD&limit=10`
- `GET /events/breaking?since_minutes=180&limit=20`
- `GET /events/{event_id}`

These endpoints read from the configured SQLAlchemy session/database.

## Database and Alembic

Important files/directories:

- `src/news_system/db/models.py` — SQLAlchemy models.
- `src/news_system/db/session.py` — session/engine setup.
- `src/news_system/storage/` — repository helpers.
- `alembic.ini` — Alembic config.
- `alembic/versions/0001_create_news_tables.py` — initial migration.

Default Alembic URL in `alembic.ini`:

```text
postgresql+psycopg://news:news@localhost:5432/news
```

Apply migrations only after confirming the target database and credentials:

```bash
UV_PROJECT_ENVIRONMENT=.venv uv run alembic upgrade head
```

## Main directories

- `src/news_system/collectors/` — collectors for configured sources.
- `src/news_system/processors/` — normalization, de-duplication, event clustering, scoring, breaking detection.
- `src/news_system/jobs/` — orchestration functions used by the CLI.
- `src/news_system/api/` — FastAPI app.
- `scripts/` — repo-local cron/Hermes shell wrappers.
- `src/news_system/db/` — database models and session setup.
- `src/news_system/storage/` — persistence/repository helpers.
- `tests/` — pytest unit tests.
- `alembic/` — database migration scripts.
- `docs/` — documentation.

## Common cautions

- Do not reintroduce old generated/runtime directories named `data/` or `legacy/` unless the user explicitly asks for new runtime output behavior.
- Do not rename the internal package namespace from `news_system` without a separate migration plan.
- Do not confuse package-name normalization in lockfiles or wheels with the required `pyproject.toml` name.
- Keep README.md in English and `docs/README_CN.md` as the matching Traditional Chinese version.
- This repo currently has no LLM, Discord, frontend, or multi-agent runtime; do not document those as implemented features.
- Do not commit changes unless explicitly instructed.
