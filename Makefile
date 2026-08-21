.PHONY: setup lint typecheck test mcp mcp-down ingest validate sync backtest pipeline clean

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

validate:
	uv run python scripts/validate.py --symbol $(SYMBOL)

sync:
	uv run python scripts/sync_catalog.py --symbol $(SYMBOL)

backtest:
	uv run python scripts/backtest.py --symbol $(SYMBOL)

pipeline: ingest validate sync backtest

clean:
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache
