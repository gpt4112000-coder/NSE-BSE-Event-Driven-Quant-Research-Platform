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
