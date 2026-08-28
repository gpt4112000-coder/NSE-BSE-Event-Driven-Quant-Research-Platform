.PHONY: setup lint typecheck test mcp mcp-down ingest validate sync backtest events crosscheck status signals cluster-backtest deflate paper update pipeline clean

TODAY_IST := $(shell TZ=Asia/Kolkata date +%Y-%m-%d)
FROM ?= $(TODAY_IST)
TO ?= $(TODAY_IST)

setup:
	uv venv --allow-existing && uv pip install -e ".[dev]"

lint:
	uv run ruff check src tests scripts

typecheck:
	uv run mypy src/indian_quant

test:
	uv run pytest

mcp:
	cd /tmp && npx -y nse-bse-mcp &

mcp-down:
	pkill -f nse-bse-mcp || true

ingest:
	uv run python scripts/ingest.py --symbol $(SYMBOL) --from $(FROM) --to $(TO)

events:
	uv run python scripts/ingest.py --symbol $(SYMBOL) --from $(FROM) --to $(TO)

validate:
	uv run python scripts/validate.py --symbol $(SYMBOL)

sync:
	uv run python scripts/sync_catalog.py --symbol $(SYMBOL)

backtest:
	uv run python scripts/backtest.py --symbol $(SYMBOL)

study:
	uv run python scripts/event_study.py --symbol $(SYMBOL)

crosscheck:
	uv run python scripts/crosscheck.py --symbol $(SYMBOL)

status:
	uv run python scripts/status_report.py

signals:
	uv run python scripts/daily_signals.py

cluster-backtest:
	uv run python scripts/cluster_backtest.py

deflate:
	uv run python scripts/deflation_check.py

web:
	uv run python scripts/run_web.py

suggestions:
	uv run python scripts/suggestion_manager.py record
	uv run python scripts/suggestion_manager.py settle
	uv run python scripts/suggestion_manager.py report

paper:
	uv run python scripts/paper_track.py snapshot
	uv run python scripts/paper_track.py settle
	uv run python scripts/paper_track.py report

# ---- Evening cycle (after ~18:30 IST, once NSE publishes bhavcopy) ----
update:
	@echo "=== make update | window $(FROM)..$(TO) (IST today: $(TODAY_IST)) ==="
	uv run python scripts/bulk_ingest.py --from $(FROM) --to $(TO)
	uv run python scripts/daily_signals.py
	uv run python scripts/paper_track.py settle || true
	uv run python scripts/paper_track.py snapshot
	uv run python scripts/suggestion_manager.py settle || true
	uv run python scripts/suggestion_manager.py record || true
	uv run python scripts/watchlist_signal_update.py || true
	uv run python scripts/status_report.py
	@echo "=== update complete ==="

pipeline: ingest validate sync backtest

clean:
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache
