#!/bin/sh
# Cron/Hermes wrapper for detecting breaking events.

set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/cron_common.sh"

LOOKBACK=${1:-${LOOKBACK_MINUTES:-60}}

run_daily_news watch-breaking --lookback-minutes "$LOOKBACK"
