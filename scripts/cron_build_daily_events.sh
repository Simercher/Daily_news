#!/bin/sh
# Cron/Hermes wrapper for building/scoring daily events.

set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/cron_common.sh"

LOOKBACK=${1:-${LOOKBACK_HOURS:-24}}
EVENT_LIMIT=${2:-${LIMIT:-10}}

run_daily_news build-events --lookback-hours "$LOOKBACK" --limit "$EVENT_LIMIT"
