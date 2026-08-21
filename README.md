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
make ingest SYMBOL=RELIANCE FROM=2025-01-01 TO=2026-08-20
make validate SYMBOL=RELIANCE
make sync SYMBOL=RELIANCE
make backtest SYMBOL=RELIANCE
```

**Verified against live NSE data (Aug 2026):** bars come from the NSE archives
CDN (UDiFF bhavcopy — the quote APIs are bot-blocked), corporate actions and
announcements via MCP. Real run: 404 validated RELIANCE daily bars,
2 corporate actions, 81 announcements, 327-fill SMA backtest, event study over
73 in-sample announcement events.

## Tests

```bash
make test
```

## Layout

See `docs/architecture.md` for the full design and `docs/data-contracts.md` for field-level
semantics of every contract.
