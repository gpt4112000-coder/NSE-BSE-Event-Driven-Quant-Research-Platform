# Architecture

## Principle

> **NSE/BSE tells us what happened. Our data layer makes it trustworthy.
> Nautilus tells us how a strategy would have behaved. Upstox tells us how the
> system behaves against a broker interface.**

Three external systems, three strictly separated roles:

| System | Role | Boundary |
|---|---|---|
| [nse-bse-mcp](https://github.com/bshada/nse-bse-mcp) | upstream research data source (60 tools: historical, corporate actions, announcements, bhavcopy) | acquisition only; never the runtime trading bus |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | event-driven backtest/simulation engine | dependency, never forked |
| Upstox API | live market data feed V3 + sandbox execution | connectivity layer behind adapter interfaces |

## Data flow

```
NSE/BSE MCP ──► Ingestion ──► Raw Store (immutable, content-addressed)
                                    │
                                    ▼
                             Normalization ──► Quality Engine
                                    │                │
                                    ▼                ▼
                              Validated layer   Quality reports (metadata DB)
                                    │
                                    ▼
                          Nautilus ParquetDataCatalog
                                    │
                                    ▼
                        BacktestEngine + Strategy
```

## Layers

### 1. Contracts (`src/indian_quant/schemas/`)

Pydantic v2 models are the single source of truth: `InstrumentIdentity`,
`MarketBar`, `CorporateAction`, `Announcement`, `OptionInstrument`,
`OptionQuote`. Nothing enters normalized/validated layers without conforming.
JSON Schema exports live in `schemas/`.

Canonical instrument id: `{EXCHANGE}_{SEGMENT}|{LOCAL_ID}` — e.g.
`NSE_EQ|RELIANCE`, `BSE_EQ|500325`, `NSE_FO|BANKNIFTY-2026-09-24-CE-52000`.
This makes NSE-equity / NSE-F&O / BSE collisions impossible by construction.

### 2. Storage (`src/indian_quant/storage/`)

- **RawStore**: immutable, content-addressed (sha256) upstream payloads with a
  `.meta.json` sidecar per record. Ground truth for reproducibility.
- **ParquetStore**: schema-enforced typed datasets under
  `data/{normalized,validated}/bars_{timeframe}/{EXCHANGE}/{SYMBOL}.parquet`.
- **ResearchDB**: DuckDB views *over* the parquet lake — SQL without moving data.
- **MetadataStore**: operational metadata only (instruments, jobs, runs,
  quality reports). Never OHLCV rows. SQLite today; Postgres-ready DSN design.

### 3. Ingestion (`src/indian_quant/ingestion/`)

`NseBseMcpClient` speaks JSON-RPC 2.0 Streamable HTTP to nse-bse-mcp (handles
plain JSON and SSE frames, session headers, retries). `NseIngestionService`
maps tool calls into contracts: every acquisition persists the exact response
to RawStore *before* parsing, and every parsed contract carries lineage
(`source`, `raw_hash`, source/ingestion timestamps).

Upstream field naming varies; parsing accepts explicit alias lists only and
routes unknown keys into `extra` so nothing silently mixes.

### 4. Normalization & quality

Deduplication, corporate-action back-adjustment (splits/bonuses by ex-date),
resampling, IST→UTC normalization. The quality engine validates OHLC
consistency, detects duplicates/conflicts, >35% price jumps and unexplained
missing sessions (holiday-aware), producing reports stored in metadata.

### 5. Nautilus integration (`src/indian_quant/nautilus/`)

- `instruments/mapping.py`: canonical → Nautilus domain objects
  (`Equity` with INR currency, `OptionContract`, `Bar`).
- `data/catalog.py`: bridge into Nautilus `ParquetDataCatalog`.
- `adapters/backtest.py`: venue/account setup, engine assembly, run,
  fills/positions/account reports, experiment registration.

Verified against nautilus_trader 1.231.0.

### 6. Research (`src/indian_quant/{features,research}/`)

Features (momentum, realized vol, volume z-score, delivery anomaly, regime)
and event studies (announcement timestamps → abnormal returns over
[-pre,+post] windows → CAR distribution → t-stat/p-value). Every experiment is
registered in the metadata store with config hash + dataset hash.

### 7. Adapters (`src/indian_quant/adapters/upstox/`)

REST historical V3 works today (candles → canonical bars, raw-persisted).
WebSocket feed V3 and sandbox execution are scaffolded behind stable
interfaces — see `adapter.md`.

## What we deliberately do NOT do

- No fork of NautilusTrader.
- No strategy code touching HTTP APIs directly — strategies consume Nautilus
  data events only.
- No OHLCV in the metadata database.
- No generic `{"value": ...}` dictionaries crossing layer boundaries.
