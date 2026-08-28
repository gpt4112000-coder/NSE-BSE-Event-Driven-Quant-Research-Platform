#!/usr/bin/env bash
# setup_cron.sh — Install daily cron jobs for the NSE-BSE Quant Platform
#
# Schedule (IST):
#   08:00  Start platform (web + MCP + backfill)
#   16:00  Stop platform (market closed, save resources)
#   18:00  Evening update (ingest bhavcopy + signals + suggestions)
#   21:00  Stop platform (done for the day)
#
# Usage:
#   ./setup_cron.sh           # Install cron jobs
#   ./setup_cron.sh --remove  # Remove all platform cron jobs
#   ./setup_cron.sh --list    # Show current schedule
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="/tmp/nse-platform-cron"
mkdir -p "$LOG_DIR"

# ── Colors ──────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

# ── Handle flags ────────────────────────────────────────────────────────
if [ "${1:-}" = "--remove" ]; then
    crontab -l 2>/dev/null | grep -v "nse-platform" | crontab - 2>/dev/null || true
    echo -e "${GREEN}✓ Removed all nse-platform cron jobs${NC}"
    exit 0
fi

if [ "${1:-}" = "--list" ]; then
    echo -e "${CYAN}Current nse-platform cron schedule:${NC}"
    crontab -l 2>/dev/null | grep "nse-platform" || echo "  (none installed)"
    echo
    echo -e "${CYAN}Schedule (IST):${NC}"
    echo "  08:00  Start platform (web + MCP + backfill)"
    echo "  16:00  Stop platform (market closed)"
    echo "  18:00  Evening update (ingest + signals + suggestions)"
    echo "  21:00  Stop platform (done for the day)"
    exit 0
fi

# ── Build crontab entry ─────────────────────────────────────────────────
CRON_TAG="nse-platform"

# Remove old entries first
(crontab -l 2>/dev/null | grep -v "$CRON_TAG") | crontab - 2>/dev/null || true

# Build new entries
NEW_CRON=$(cat <<EOF
# ── NSE-BSE Quant Platform — Daily Schedule (IST) ──────────────────────
# Start platform at 08:00 IST (before market opens)
0 8 * * * cd $ROOT && ./start_platform.sh >> $LOG_DIR/start.log 2>&1 # $CRON_TAG-start

# Stop platform at 16:00 IST (after market closes, save resources)
0 16 * * * cd $ROOT && ./stop_platform.sh >> $LOG_DIR/stop.log 2>&1 # $CRON_TAG-stop-pm

# Evening update at 18:00 IST (bhavcopy available ~18:30)
0 18 * * * cd $ROOT && make update >> $LOG_DIR/update.log 2>&1 # $CRON_TAG-update

# Stop platform at 21:00 IST (done for the day)
0 21 * * * cd $ROOT && ./stop_platform.sh >> $LOG_DIR/stop.log 2>&1 # $CRON_TAG-stop-night
EOF
)

# Append to existing crontab (or create new)
(crontab -l 2>/dev/null; echo "$NEW_CRON") | crontab -

echo -e "${GREEN}✓ Cron jobs installed!${NC}"
echo
echo -e "${CYAN}Schedule (IST):${NC}"
echo "  08:00  Start platform (web + MCP + backfill)"
echo "  16:00  Stop platform (market closed)"
echo "  18:00  Evening update (ingest + signals + suggestions)"
echo "  21:00  Stop platform (done for the day)"
echo
echo -e "${CYAN}Logs:${NC} $LOG_DIR/"
echo "  start.log   — morning startup"
echo "  stop.log    — shutdown"
echo "  update.log  — evening data refresh"
echo
echo -e "${YELLOW}Verify with:${NC} crontab -l | grep nse-platform"
echo -e "${YELLOW}Remove with:${NC} $0 --remove"
echo -e "${YELLOW}View logs:${NC}   tail -f $LOG_DIR/update.log"
