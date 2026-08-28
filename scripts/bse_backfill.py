"""Backfill BSE bars_1d using yfinance (3 months history).

BSE bhavcopy only provides ~6 days. yfinance provides 67+ days.
This gives us enough data for RSI (14d), SMA (20d), MACD (26d).

Usage:
    python scripts/bse_backfill.py              # backfill all BSE stocks
    python scripts/bse_backfill.py --limit 50   # backfill first 50
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
import yfinance as yf

from indian_quant.config import load_settings
from indian_quant.storage.parquet_store import ParquetStore

BOND_RE = re.compile(r"^\d+[A-Z]|^[A-Z]*\d{4,}|^GS|^GOI|^SDL|^TB\d|^T\d{2}")


def backfill_symbol(symbol: str, store: ParquetStore) -> bool:
    """Download 3mo BSE data for one symbol and write via ParquetStore."""
    try:
        ticker = yf.Ticker(f"{symbol}.BO")
        hist = ticker.history(period="3mo")
        if hist is None or hist.empty or len(hist) < 3:
            return False

        df = pd.DataFrame({
            "timestamp": hist.index.tz_localize(None),
            "open": hist["Open"].values,
            "high": hist["High"].values,
            "low": hist["Low"].values,
            "close": hist["Close"].values,
            "volume": hist["Volume"].values,
        })
        df["instrument_id"] = f"BSE_EQ|{symbol}"
        df["exchange"] = "BSE"
        df["timeframe"] = "1d"

        store.write_frame(df, layer="normalized", dataset="bars_1d", exchange="BSE", name=symbol)
        return True
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill BSE bars via yfinance")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of symbols")
    args = parser.parse_args()

    settings = load_settings()
    store = ParquetStore(settings.data_root, settings.storage.parquet_compression)

    reg = json.loads((settings.data_root / "universe" / "registry.json").read_text())
    bse_syms = sorted(sym for sym, v in reg.get("symbols", {}).items()
                      if v.get("exchange") == "BSE"
                      and v.get("segment") in ("EQ", "SME")
                      and not BOND_RE.match(sym))

    if args.limit > 0:
        bse_syms = bse_syms[: args.limit]

    skip = 0
    to_backfill = []
    bse_dir = settings.normalized_dir / "bars_1d" / "BSE"
    for sym in bse_syms:
        p = bse_dir / f"{sym}.parquet"
        if p.exists() and len(pd.read_parquet(p)) >= 20:
            skip += 1
        else:
            to_backfill.append(sym)

    print(json.dumps({
        "total_bse": len(bse_syms),
        "already_sufficient": skip,
        "to_backfill": len(to_backfill),
    }))

    t0 = time.time()
    success = 0
    fail = 0

    for i, sym in enumerate(to_backfill):
        ok = backfill_symbol(sym, store)
        if ok:
            success += 1
        else:
            fail += 1
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            print(f"  {i+1}/{len(to_backfill)} done, {success} ok, {fail} fail ({elapsed:.0f}s)", flush=True)
            time.sleep(0.5)

    elapsed = time.time() - t0
    print(json.dumps({
        "backfilled": success,
        "failed": fail,
        "skipped": skip,
        "time": f"{elapsed:.0f}s",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
