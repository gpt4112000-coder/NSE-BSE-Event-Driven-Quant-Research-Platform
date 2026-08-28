#!/usr/bin/env bash
# stop_platform.sh — Cleanly shut down all platform processes
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

STOPPED=0

echo "Stopping NSE-BSE Quant Platform..."
echo

# 1. Web dashboard (uvicorn on 8080)
if fuser 8080/tcp >/dev/null 2>&1; then
    echo -e "  ${YELLOW}▸${NC} Web dashboard (port 8080)..."
    fuser -k 8080/tcp 2>/dev/null || true
    sleep 1
    STOPPED=$((STOPPED + 1))
    echo -e "    ${GREEN}✓ stopped${NC}"
else
    echo -e "  ${YELLOW}▸${NC} Web dashboard — ${RED}not running${NC}"
fi

# 2. Announcements backfill
if pgrep -f "announcements_backfill" >/dev/null 2>&1; then
    echo -e "  ${YELLOW}▸${NC} Announcements backfill..."
    pkill -f "announcements_backfill" 2>/dev/null || true
    sleep 1
    STOPPED=$((STOPPED + 1))
    echo -e "    ${GREEN}✓ stopped${NC}"
else
    echo -e "  ${YELLOW}▸${NC} Announcements backfill — ${RED}not running${NC}"
fi

# 3. MCP server (nse-bse-mcp)
if pgrep -f "nse-bse-mcp" >/dev/null 2>&1; then
    echo -e "  ${YELLOW}▸${NC} MCP server (nse-bse-mcp)..."
    pkill -f "nse-bse-mcp" 2>/dev/null || true
    sleep 2
    STOPPED=$((STOPPED + 1))
    echo -e "    ${GREEN}✓ stopped${NC}"
else
    echo -e "  ${YELLOW}▸${NC} MCP server — ${RED}not running${NC}"
fi

# 4. Any stale paper_track / daily_signals / suggestion_manager
for proc in paper_track daily_signals suggestion_manager bulk_ingest signal_sweep; do
    if pgrep -f "$proc" >/dev/null 2>&1; then
        echo -e "  ${YELLOW}▸${NC} Stale $proc process..."
        pkill -f "$proc" 2>/dev/null || true
        STOPPED=$((STOPPED + 1))
        echo -e "    ${GREEN}✓ stopped${NC}"
    fi
done

echo
if [ "$STOPPED" -gt 0 ]; then
    echo -e "${GREEN}Done${NC} — stopped $STOPPED process(es)."
else
    echo -e "${GREEN}Done${NC} — nothing was running."
fi
