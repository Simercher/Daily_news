#!/bin/sh
# Shared helpers for Daily_news cron wrappers. Source from wrapper scripts only.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

# Load repo-local .env if present, but do not override variables already
# supplied by the cron/Hermes environment (DATABASE_URL, API keys, etc.).
load_dotenv_preserve_env() {
    env_file=$REPO_ROOT/.env
    [ -f "$env_file" ] || return 0

    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            ''|'#'*) continue ;;
            export\ *) line=${line#export } ;;
        esac
        case "$line" in
            *=*) ;;
            *) continue ;;
        esac
        key=${line%%=*}
        value=${line#*=}
        case "$key" in
            ''|*[!A-Za-z0-9_]*) continue ;;
            [0-9]*) continue ;;
        esac
        if eval '[ "${'"$key"'+set}" = set ]'; then
            continue
        fi
        eval "export $key=$value"
    done < "$env_file"
}

run_daily_news() {
    load_dotenv_preserve_env
    : "${UV_PROJECT_ENVIRONMENT:=.venv}"
    export UV_PROJECT_ENVIRONMENT
    cd "$REPO_ROOT"
    exec uv run daily-news "$@"
}
