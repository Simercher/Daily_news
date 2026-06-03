#!/bin/sh
# Cron/Hermes wrapper for collecting recent news articles.

set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/cron_common.sh"

SOURCE=${1:-${NEWS_SOURCE:-all}}
LOOKBACK=${2:-${LOOKBACK_HOURS:-1}}

run_daily_news collect --source "$SOURCE" --lookback-hours "$LOOKBACK"
