# Adapter Guide (Upstox)

How the Upstox integration is structured and how to take it from scaffold to
production. The design follows NautilusTrader's own adapter philosophy:
protocol behavior lives in the adapter; the platform supplies domain
contracts. We do not fork NautilusTrader.

## Current state

| Component | Status | Location |
|---|---|---|
| Auth CLI (`login`/`refresh`/`whoami`) | **working** (live-verified) | `scripts/upstox_auth.py` |
| REST Historical Candle V3 | **live-verified** - 30d RELIANCE, 0.0000% drift vs NSE bhavcopy | `adapters/upstox/rest.py` |
| Crosscheck pair `nse_cm_vs_upstox` | **working** | `scripts/crosscheck.py` |
| Feed V3 protobuf decoder | **implemented** - official schema, fixture-tested; live recording pending market hours | `adapters/upstox/feed.py` + `proto/` |
| Sandbox execution lifecycle | implemented against V3 endpoints, mock-tested; live sandbox run needs a console-generated sandbox token | `adapters/upstox/execution.py` |
| Reconciliation (C1) | **live-read-verified** (orders/positions/funds IO) | `adapters/upstox/reconciliation.py` |

Sandbox tokens: created in the developer console's sandbox section
(one per user, 30-day validity, no browser OAuth). Set via
`UPSTOX_SANDBOX_TOKEN` or `upstox_sandbox_tokens.json`.

## REST Historical V3 (working)

```
GET https://api.upstox.com/v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}
Authorization: Bearer {access_token}
→ data.candles: [[ts, open, high, low, close, volume, oi], ...]
```

- Instrument keys are canonical Upstox ids (`NSE_EQ|INE002A01018`) — same
  shape as our canonical instrument ids by design.
- Units: minutes (1–300, from Jan 2022), hours (1–5, quarter window), days/
  weeks/months (1, back to Jan 2000).
- Every response is persisted to RawStore before parsing.

```python
client = UpstoxRestClient(access_token=os.environ["UPSTOX_ACCESS_TOKEN"])
bars = client.get_bars(
    instrument_key="NSE_EQ|INE002A01018",
    instrument_id="NSE_EQ|RELIANCE",
    timeframe=Timeframe.DAY,
    to_date=date(2025, 6, 30),
)
```

Historical research data still comes primarily from NSE/BSE via MCP;
Upstox historical is a supplementary/verification source.

## WebSocket Feed V3 (Phase 6)

`wss://api.upstox.com/v3/feed/market-data-feed`, protobuf binary frames,
modes: `ltpc`, `option_greeks`, `full`, `full_d30`.

`UpstoxFeedClient` owns connection lifecycle, subscription management
(`subscribe(instrument_keys, mode)`) and frame dispatch. Binary decoding is
delegated to a pluggable `FeedDecoder`. To finish Phase 6:

1. Generate protobuf classes from Upstox's published `.proto` feed schema
   (`pip install upstox-python-sdk` or compile `MarketDataFeedV3.proto` with
   `grpcio-tools`).
2. Implement `FeedDecoder.decode()` returning normalized record dicts.
3. Map records → Nautilus `QuoteTick`/`TradeTick`/`Bar` events through
   `nautilus/instruments/mapping.py`.
4. Exit condition: the same strategy runs unchanged against historical replay
   and the live stream — only the data source config changes.

## Sandbox execution (Phase 7)

`UpstoxExecutionClient` mirrors Nautilus's ExecutionClient concepts:

```
connect / generate_account_state / submit_order /
modify_order / cancel_order / reconcile
```

Guardrails already enforced in code:
- constructing with `sandbox=False` raises — live routing is impossible by accident;
- every lifecycle method raises `NotImplementedError("Phase 7")`.

Test matrix when implementing: submit, modify, cancel, partial fill, fill,
reject, timeout, disconnect/reconnect, duplicate event, reconciliation after
restart.

## Rust adapter path (optional, later)

If Python-side latency ever becomes the bottleneck, the Nautilus adapter
developer guide prescribes an out-of-tree Rust crate layout:

```
rust/upstox_adapter/
├── Cargo.toml
├── src/{common,http,websocket,config,data,execution,factories,python}
└── tests/
```

Implementation sequence per Nautilus docs: scope → protocol core →
instruments → data → execution → reconciliation → conformance testing.
The Python package here remains the reference implementation either way.

## Credentials

Never hardcode tokens. Environment variables (see `configs/sandbox.yaml`):

```
UPSTOX_API_KEY=...
UPSTOX_ACCESS_TOKEN=...
```

`UpstoxConfig.resolve_token()` reads them at runtime only.
