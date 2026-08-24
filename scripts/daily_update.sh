#!/usr/bin/env bash
# Cron wrapper for the 18:30 IST evening cycle.
# Suggested crontab entry (weekdays only):
#   45 18 * * 1-5 /bin/bash "<repo>/scripts/daily_update.sh"
set -u
cd "$(dirname "$0")/.." || exit 1

mkdir -p logs
LOG="logs/update-$(date +%F).log"

{
  echo "=== make update $(date -Is) ==="
  make update
  code=$?
  echo "=== exited $code at $(date -Is) ==="
} >> "$LOG" 2>&1
exit $code
