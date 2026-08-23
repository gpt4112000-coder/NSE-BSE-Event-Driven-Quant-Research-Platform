# Operations

## Setup

```bash
make setup                      # uv venv + editable install with dev tools
docker compose up -d mcp        # nse-bse-mcp on :3000 (Streamable HTTP)
docker compose up -d postgres   # optional: metadata DB beyond sqlite
cp configs/sandbox.yaml configs/local.yaml   # then edit; never commit secrets
```

## Daily pipeline

```bash
make ingest  SYMBOL=RELIANCE FROM=2024-01-01 TO=2025-01-01
make validate SYMBOL=RELIANCE
make sync    SYMBOL=RELIANCE
make backtest SYMBOL=RELIANCE
```

`make pipeline SYMBOL=... FROM=... TO=...` chains all four.

Exit codes: `validate.py` returns non-zero when the quality report has errors,
so it can gate CI or scheduling.

## Health checks

- MCP server: `curl http://localhost:3000/health` (or run any tool).
- Data freshness: `duckdb data/research.duckdb -c "SELECT max(timestamp) FROM validated_bars"`.
- Job history & quality reports live in `data/metadata.db`
  (`jobs`, `quality_reports`, `runs` tables).

## Reproducibility rules

1. Raw payloads are immutable and content-addressed; never edit `data/raw`.
2. Every experiment/backtest records `(config_hash, dataset_hash, metrics)`
   in the metadata store. Re-running the same pair must reproduce metrics.
3. Quality gates: a dataset is "trusted" only after passing the quality suite;
   strategies consume only `validated/` → catalog data.

## Failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| ingest returns "no bars" | MCP server down | `make mcp` / `docker compose up mcp` |
| backtest: "no instruments in catalog" | sync step skipped | `make sync SYMBOL=...` |
| validate exits 2 | real data-quality errors | inspect report JSON printed above |
| MCP timeout/retries exhausted | NSE rate limiting | increase `mcp.timeout_seconds`, reduce request rate |

## Daily Upstox login

```bash
uv run python scripts/upstox_auth.py url      # print login URL
# open URL, log in (chilakammanaru@gmail.com / naru app),
# copy full redirected URL (contains ?code=...)
uv run python scripts/upstox_auth.py login    # paste when prompted
uv run python scripts/upstox_auth.py whoami   # verify
```
If a refresh token was stored: `scripts/upstox_auth.py refresh` skips the browser.
Tokens expire ~03:30 IST daily.

## Kill switch (C2)

Backtests/live engines enforce RiskEngine limits from `configs/*.yaml`
(`backtest.risk_*`). To halt trading at runtime: set engine trader state to
HALT (`trader.stop()` in live; kill process for backtest) and investigate via
reconciliation before resuming:

```bash
uv run python scripts/crosscheck.py --symbol RELIANCE     # data sanity
uv run python -c "from indian_quant.adapters.upstox.reconciliation import Reconciler; ..."
```

Any reconciliation mismatch => do not resume until resolved.

## Observability (C3)

```bash
uv run python scripts/metrics.py            # Prometheus text snapshot
uv run python scripts/metrics.py --serve 9108
```
Structured JSON logging: `from indian_quant.config.logging_setup import setup_logging; setup_logging(json_mode=True)`.

## Shadow session (B4)

Monday during market hours:
```bash
uv run python scripts/shadow_session.py --keys "NSE_EQ|INE002A01018" --minutes 60 --mode full
```
Recording lands under `data/raw/upstox/feed_sessions/<id>/`; parity harness
consumes it next.

## Upgrading nautilus_trader

The integration pins behavior against specific Nautilus APIs (verified on
1.231.0): `BacktestEngine.add_venue` before `add_instrument`,
`BarType(id, spec, AggregationSource.EXTERNAL)`, trader report methods.
After upgrading, run `pytest tests/integration` first — those tests encode the
verified API surface.

## Security

- Tokens only via env vars (`UPSTOX_ACCESS_TOKEN`); `.env*` gitignored.
- Execution client refuses non-sandbox construction until Phase 8 sign-off.
- Raw store and metadata DB contain no credentials.
