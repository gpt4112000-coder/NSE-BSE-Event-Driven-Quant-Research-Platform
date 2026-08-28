"""Pre-compute and cache all delivery signals in SQLite.

Scans ALL NSE + BSE parquet files once, computes features, writes to
cached_signals table. Dashboard/Signals pages read from this table
instead of scanning 3,755+ parquet files on every request.

Usage:
    python scripts/cache_signals.py              # full rebuild
    python scripts/cache_signals.py --incremental  # only new dates

Run daily after market close via APScheduler or cron.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
import sqlalchemy as sa

from indian_quant.config import load_settings
from indian_quant.features.delivery import add_features, prepare_frame


def get_engine(db_path: str):
    return sa.create_engine(f"sqlite:///{db_path}")


def ensure_table(engine):
    meta = sa.MetaData()
    sa.Table(
        "cached_signals", meta,
        sa.Column("symbol", sa.String, primary_key=True),
        sa.Column("exchange", sa.String, nullable=False),
        sa.Column("signal_date", sa.String),
        sa.Column("segment", sa.String),
        sa.Column("close", sa.Float),
        sa.Column("prev_close", sa.Float),
        sa.Column("ret_1d_pct", sa.Float),
        sa.Column("deliv_pct", sa.Float),
        sa.Column("deliv_z", sa.Float),
        sa.Column("vol_z", sa.Float),
        sa.Column("rsi", sa.Float),
        sa.Column("macd", sa.Float),
        sa.Column("macd_signal", sa.Float),
        sa.Column("sma_20", sa.Float),
        sa.Column("sma_50", sa.Float),
        sa.Column("atr_14", sa.Float),
        sa.Column("hi_streak", sa.Integer),
        sa.Column("signal_type", sa.String),
        sa.Column("entry_zone_low", sa.Float),
        sa.Column("entry_zone_high", sa.Float),
        sa.Column("stop_loss", sa.Float),
        sa.Column("target_price", sa.Float),
        sa.Column("volume", sa.Float),
        sa.Column("cached_at", sa.String),
        sa.Column("raw_json", sa.String),
    )
    meta.create_all(engine)


def compute_signal_for_stock(parquet_path: Path, symbol: str, exchange: str) -> dict | None:
    try:
        raw = pd.read_parquet(parquet_path)
        if raw.empty or len(raw) < 20:
            return None

        frame = prepare_frame(raw, min_rows=min(20, len(raw)))
        if frame is None or frame.empty:
            return None

        frame = add_features(frame)
        if frame.empty:
            return None

        last = frame.iloc[-1]
        prev = frame.iloc[-2] if len(frame) > 1 else frame.iloc[-1]

        signal_type = None
        if pd.notna(last.get("deliv_z")) and pd.notna(last.get("ret_1d")):
            if last["deliv_z"] >= 2 and last["ret_1d"] >= 0.005:
                signal_type = "dz_hi_up"
            elif last["deliv_z"] >= 2 and last["ret_1d"] <= -0.005:
                signal_type = "dz_hi_dn"
            elif last["deliv_z"] <= -2 and last["ret_1d"] >= 0.005:
                signal_type = "dz_lo_up"

        close = float(last["close"])
        prev_close = float(prev["close"]) if pd.notna(prev.get("close")) else close
        ret_1d_pct = round((close / prev_close - 1) * 100, 2) if prev_close > 0 else 0
        atr = float(last.get("atr_14", close * 0.03)) if pd.notna(last.get("atr_14")) else close * 0.03

        return {
            "symbol": symbol,
            "exchange": exchange,
            "signal_date": str(pd.to_datetime(last["date"]).date()),
            "segment": str(last.get("segment", "EQ")),
            "close": round(close, 2),
            "prev_close": round(prev_close, 2),
            "ret_1d_pct": ret_1d_pct,
            "deliv_pct": round(float(last["deliv_pct"]), 1) if pd.notna(last.get("deliv_pct")) else None,
            "deliv_z": round(float(last["deliv_z"]), 2) if pd.notna(last.get("deliv_z")) else None,
            "vol_z": round(float(last["vol_z"]), 2) if pd.notna(last.get("vol_z")) else None,
            "rsi": round(float(last["rsi"]), 1) if pd.notna(last.get("rsi")) else None,
            "macd": round(float(last["macd"]), 2) if pd.notna(last.get("macd")) else None,
            "macd_signal": round(float(last["macd_signal"]), 2) if pd.notna(last.get("macd_signal")) else None,
            "sma_20": round(float(last["sma_20"]), 2) if pd.notna(last.get("sma_20")) else None,
            "sma_50": round(float(last["sma_50"]), 2) if pd.notna(last.get("sma_50")) else None,
            "atr_14": round(atr, 2),
            "hi_streak": int(last.get("hi_streak", 0)) if pd.notna(last.get("hi_streak")) else 0,
            "signal_type": signal_type,
            "entry_zone_low": round(close - atr * 0.5, 2),
            "entry_zone_high": round(close, 2),
            "stop_loss": round(close * 0.93, 2),
            "target_price": round(close * 1.05, 2),
            "volume": float(last.get("volume", 0)) if pd.notna(last.get("volume")) else 0,
        }
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Cache delivery signals")
    parser.add_argument("--incremental", action="store_true",
                        help="Only update stocks with stale data")
    parser.add_argument("--config", default=None)
    parser.parse_args()

    settings = load_settings()
    db_path = str(Path(settings.storage.metadata_dsn.removeprefix("sqlite:///")))
    engine = get_engine(db_path)
    ensure_table(engine)

    nse_dir = settings.normalized_dir / "delivery" / "NSE"
    bse_dir = settings.normalized_dir / "delivery" / "BSE"

    t0 = time.time()
    signals = []

    # Scan NSE
    if nse_dir.exists():
        for p in sorted(nse_dir.glob("*.parquet")):
            sig = compute_signal_for_stock(p, p.stem, "NSE")
            if sig:
                signals.append(sig)

    # Scan BSE
    if bse_dir.exists():
        for p in sorted(bse_dir.glob("*.parquet")):
            sig = compute_signal_for_stock(p, p.stem, "BSE")
            if sig:
                signals.append(sig)

    elapsed_scan = time.time() - t0

    # Write to cache
    if signals:
        df = pd.DataFrame(signals)
        df["cached_at"] = pd.Timestamp.now(tz="UTC").isoformat()
        df.to_sql("cached_signals", engine, if_exists="replace", index=False)

    elapsed_total = time.time() - t0
    buys = sum(1 for s in signals if s.get("signal_type") == "dz_hi_up")
    avoids = sum(1 for s in signals if s.get("signal_type") == "dz_hi_dn")

    print(json.dumps({
        "total_stocks": len(signals),
        "buys": buys,
        "avoids": avoids,
        "scan_time": f"{elapsed_scan:.1f}s",
        "total_time": f"{elapsed_total:.1f}s",
        "db_path": db_path,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
