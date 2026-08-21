# NSE-BSE Event-Driven Quant Research Platform

> **Live animated documentation:** https://kondaiahpola1-wq.github.io/NSE-BSE-Event-Driven-Quant-Research-Platform/ (mirror: https://gpt4112000-coder.github.io/NSE-BSE-Event-Driven-Quant-Research-Platform/)

Indian quant research & market infrastructure built around three external systems:

| System | Role |
|---|---|
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | event-driven backtesting/simulation engine (dependency, never forked) |
| [nse-bse-mcp](https://github.com/bshada/nse-bse-mcp) | upstream research data source (historical, corporate actions, announcements, bhavcopy) |
| Upstox API | live market data feed + sandbox execution connectivity |

**Core principle:** *NSE/BSE tells us what happened. Our data layer makes it trustworthy.
Nautilus tells us how a strategy would have behaved. Upstox tells us how the system behaves
against a broker interface.*

## Architecture

```
NSE/BSE MCP ──► Ingestion ──► Raw Store (immutable, hashed)
                                    │
                                    ▼
                             Normalization ──► Quality Engine
                                    │                │
                                    ▼                ▼
                              Validated layer   Quality reports
                                    │
                                    ▼
                          Nautilus ParquetDataCatalog
                                    │
                                    ▼
                        BacktestEngine + Strategy
```

- **Canonical contracts** (`src/indian_quant/schemas/`): `InstrumentIdentity`, `MarketBar`,
  `CorporateAction`, `Announcement`, `OptionInstrument`, `OptionQuote` — every record carries
  full lineage (`source`, `raw_hash`, timestamps).
- **Canonical instrument id**: `NSE_EQ|RELIANCE`, `BSE_EQ|500325`, `NSE_FO|BANKNIFTY-2026-09-24-CE-52000`.
  An equity can never be confused with an F&O contract or a BSE scrip.
- **Storage**: parquet lake (bars), DuckDB (research SQL over parquet), SQLite/Postgres (metadata only).
- **Adapters**: Upstox REST historical V3 works today; WebSocket feed V3 and sandbox execution
  are scaffolded behind stable interfaces (see `docs/adapter.md`).

## Quickstart

```bash
make setup                 # uv venv + install
docker compose up -d mcp   # start nse-bse-mcp on :3000
make ingest SYMBOL=RELIANCE FROM=2024-01-01 TO=2025-01-01
make validate SYMBOL=RELIANCE
make sync SYMBOL=RELIANCE
make backtest SYMBOL=RELIANCE
```

## Tests

```bash
make test
```

## Layout

See `docs/architecture.md` for the full design and `docs/data-contracts.md` for field-level
semantics of every contract.
