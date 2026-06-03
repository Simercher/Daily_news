# Hermes Cron Runbook

This runbook describes how to schedule the repo-local Step 7 wrappers with Hermes cron or an equivalent scheduler. It is documentation only: do not create cron jobs from this repository, and do not claim jobs are installed unless a separate Hermes cron action actually creates them.

## Wrappers

Use these repository-local scripts as the scheduled commands:

- `/opt/data/plugins/Daily_news/scripts/cron_collect.sh` — collect recent articles from configured sources.
- `/opt/data/plugins/Daily_news/scripts/cron_build_daily_events.sh` — build/score daily events.
- `/opt/data/plugins/Daily_news/scripts/cron_watch_breaking.sh` — detect breaking events.

The wrappers are POSIX `sh` scripts. They resolve the repository root relative to the script path, can run from any current working directory, preserve caller-provided environment variables, optionally load repo-local `.env` values without overriding the caller environment, and default `UV_PROJECT_ENVIRONMENT=.venv` when it is not already set.

## Required environment

Set `DATABASE_URL` either in the Hermes cron environment or in `/opt/data/plugins/Daily_news/.env`.

Provider API keys are optional and only needed for enabled sources that require them, such as NewsAPI. RSS and GDELT source usage may not require extra keys depending on `config/sources.yaml`.

Example environment value:

```bash
DATABASE_URL='postgresql+psycopg://daily_news:daily_news@localhost:5432/daily_news'
```

If Hermes cron runs inside a container, confirm that the database host in `DATABASE_URL` is reachable from that scheduler environment; `localhost` may refer to the container rather than the host.

## Suggested schedules

Suggested Hermes cron schedules:

| Job | Schedule | Command |
| --- | --- | --- |
| Collect | every 30 minutes | `/opt/data/plugins/Daily_news/scripts/cron_collect.sh` |
| Daily event build | 07:30 Asia/Taipei daily | `/opt/data/plugins/Daily_news/scripts/cron_build_daily_events.sh` |
| Breaking watch | every 10 minutes | `/opt/data/plugins/Daily_news/scripts/cron_watch_breaking.sh` |

For schedulers using standard five-field cron expressions:

```text
*/30 * * * *  /opt/data/plugins/Daily_news/scripts/cron_collect.sh
30 7 * * *    /opt/data/plugins/Daily_news/scripts/cron_build_daily_events.sh
*/10 * * * *  /opt/data/plugins/Daily_news/scripts/cron_watch_breaking.sh
```

`30 7 * * *` means 07:30 in the scheduler host timezone. To run the daily build at 07:30 Asia/Taipei, either configure the scheduler timezone to Asia/Taipei or translate the expression to the scheduler host timezone.

## Hermes cron CLI examples

The exact Hermes CLI flags may depend on the installed Hermes version. Conceptually, create three cron entries with the schedules and commands above, and provide `DATABASE_URL` through the cron/Hermes environment or repo `.env`.

Example commands to adapt, not run from this repository setup step:

```bash
hermes cron create \
  --name daily-news-collect \
  --schedule '*/30 * * * *' \
  --command '/opt/data/plugins/Daily_news/scripts/cron_collect.sh'

hermes cron create \
  --name daily-news-build-daily-events \
  --schedule '30 7 * * *' \
  --command '/opt/data/plugins/Daily_news/scripts/cron_build_daily_events.sh'

hermes cron create \
  --name daily-news-watch-breaking \
  --schedule '*/10 * * * *' \
  --command '/opt/data/plugins/Daily_news/scripts/cron_watch_breaking.sh'
```

If using a cronjob tool/API instead of the CLI, create equivalent entries with the same names, schedules, commands, and environment. Do not install duplicate jobs if they already exist.

## Optional overrides

The wrappers expose simple positional and environment overrides for ad hoc jobs:

```bash
# Collect a specific source over a longer lookback.
/opt/data/plugins/Daily_news/scripts/cron_collect.sh rss 24
NEWS_SOURCE=gdelt LOOKBACK_HOURS=6 /opt/data/plugins/Daily_news/scripts/cron_collect.sh

# Build events with a different lookback and limit.
/opt/data/plugins/Daily_news/scripts/cron_build_daily_events.sh 48 20
LOOKBACK_HOURS=48 LIMIT=20 /opt/data/plugins/Daily_news/scripts/cron_build_daily_events.sh

# Watch breaking events over a wider window.
/opt/data/plugins/Daily_news/scripts/cron_watch_breaking.sh 180
LOOKBACK_MINUTES=180 /opt/data/plugins/Daily_news/scripts/cron_watch_breaking.sh
```
