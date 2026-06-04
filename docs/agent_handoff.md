# Daily_news Agent Handoff

This document is the handoff/runbook for an automation agent that needs to work on the Daily_news repository while correctly distinguishing between repo-contained code and the external Hermes operational layer used in production.

## Project purpose

Daily_news is the data and processing core for a news briefing system. Inside this repository, it collects articles from configured providers, normalizes and stores article/event data, performs deterministic de-duplication, clustering, scoring, and breaking-news detection, and exposes read access through a CLI and FastAPI app.

The Python project name must remain `Daily_news` in `pyproject.toml`. The command-line entry point is `daily-news`. The internal Python package namespace is `news_system`; keep that namespace in imports and source-path references.

## Scope and repo/ops boundary

This repository contains the core pipeline logic:

- collectors for RSS, NewsAPI, and GDELT inputs;
- SQLAlchemy models and repository helpers;
- Alembic migration scaffold for PostgreSQL;
- normalization, URL de-duplication, event clustering, scoring, breaking-news detection, and domain candidate generation;
- CLI jobs and repo-local helper scripts for collection, event building, and structured candidate output;
- FastAPI read endpoints for daily, breaking, and single-event views.

Important boundary:

- **Repo-contained code**: deterministic collection, processing, storage, APIs, and structured candidate outputs.
- **Operational production layer outside this repo**: Hermes profile(s), cron scheduling, final LLM reasoning, Traditional Chinese briefing writing, final domain classification/selection, and Discord forum posting.

Therefore:

- do not describe Discord posting as a committed repo feature;
- do not describe final LLM summarization/classification as implemented inside repo code;
- do describe the production workflow as using this repo as its processing engine.

## Current operational pipeline

The current production system is split across this repo and an external Hermes operational layer.

### Daily-news flow

1. Collect articles with `daily-news collect --lookback-hours 24` or equivalent operator scheduling.
2. Generate structured domain candidates with `scripts/domain_summarizer.py --lookback-hours 24`.
3. The external Hermes profile performs final LLM reasoning, chooses domains dynamically, writes the final Traditional Chinese summary, and posts to Discord.

Operational facts that should be documented accurately:

- `scripts/domain_summarizer.py` now queries **all non-duplicate articles in the lookback window by default**.
- `--limit` is optional and only constrains the query when explicitly passed.
- The script emits structured JSON candidates plus `rule_domain` hints.
- `rule_domain` is deterministic guidance, **not** the final production domain decision.
- Final production domain selection is handled outside the repo and the number of selected items per domain is **dynamic** — typically around 4–10 articles per domain, not a fixed 5-item output.

### Breaking-news flow

1. Run fast RSS-only collection with `scripts/collect_rss_quick.py --lookback-hours 2`.
2. Run `daily-news watch-breaking --lookback-minutes 120 --limit 10`.
3. If breaking events exist, the operational layer posts to a Discord forum and notifies a dedicated thread; otherwise it remains silent.

Treat the repository as the processing engine for both daily and breaking-news workflows; Hermes handles final reasoning, formatting, and delivery.

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

Notes:

- `uv.lock` may normalize the package name to `daily-news`; that is acceptable. `pyproject.toml` must keep `name = "Daily_news"`.

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

`config/sources.yaml` is the single source configuration entry point. `daily-news collect --source all|rss|newsapi|gdelt|<name>` loads this file and collects only enabled sources.

RSS collection path to verify collection behavior:

```bash
DATABASE_URL='postgresql+psycopg://daily_news:daily_news@localhost:5432/daily_news' \
  UV_PROJECT_ENVIRONMENT=.venv uv run daily-news collect --source rss --lookback-hours 24
```

Expected JSON includes top-level `fetched`, `inserted`, `duplicates`, `filtered_old`, `source_counts`, and `errors`. Collection writes `news_sources` metadata, records `collection_runs`, normalizes/canonicalizes URLs, and upserts by unique `url_hash`. The no-explicit-session CLI path currently calls `Base.metadata.create_all(engine)` before opening a session, which is convenient for SQLite/dev smoke runs; production PostgreSQL should still be managed with Alembic migrations and an explicitly verified `DATABASE_URL`/schema.

For PostgreSQL verification, set `DATABASE_URL` explicitly and run `daily-news db-smoke`. The smoke command verifies required tables and inserts a unique source/article/event/link/collection run. `tests/test_postgres_integration.py` calls the same function and skips unless `DATABASE_URL` is present.

## Repo-local scripts and operator entry points

Currently committed `scripts/` entry points include:

```bash
# Build structured domain candidates from the last 24 hours.
UV_PROJECT_ENVIRONMENT=.venv uv run python scripts/domain_summarizer.py --lookback-hours 24

# Fast RSS-only collection for breaking monitoring.
UV_PROJECT_ENVIRONMENT=.venv uv run python scripts/collect_rss_quick.py --lookback-hours 2
```

Operator notes:

- `scripts/domain_summarizer.py` is a candidate-generation step, not the final production summarizer.
- Its output is intended for downstream Hermes automation.
- Cron scheduling and Hermes profile definitions are external operational concerns and are not committed here.
- Avoid documenting ephemeral Discord IDs or thread IDs in repo docs unless there is a strong operational reason.

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
- `alembic/versions/` — migration files.

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
- `src/news_system/processors/` — normalization, de-duplication, clustering, scoring, breaking detection, and domain summarizer logic.
- `src/news_system/jobs/` — orchestration functions used by the CLI.
- `src/news_system/api/` — FastAPI app.
- `scripts/` — repo-local helper scripts for candidate generation and fast RSS collection.
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
- When documenting capabilities, distinguish clearly between what is committed in this repo and what the production Hermes workflow adds around it.
- Do not commit changes unless explicitly instructed.
