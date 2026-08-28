"""Pre-compute and cache all delivery signals in PostgreSQL + Redis.

Architecture:
    1. Scan ALL NSE + BSE parquet files → compute features
    2. Write to PostgreSQL (persistent store)
    3. Write to Redis (hot cache, TTL=1h)
    4. Dashboard/Signals read from Redis → PostgreSQL fallback

Usage:
    python scripts/cache_signals.py              # full rebuild
    python scripts/cache_signals.py --warm-redis  # only refresh Redis from PG

Run daily after market close via APScheduler or cron.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from indian_quant.config import load_settings
from indian_quant.features.delivery import add_features, prepare_frame
from indian_quant.web.prod_config import (
    REDIS_TTL,
    ensure_pg_schema,
    get_pg_engine,
    get_redis_client,
)


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


def write_to_postgres(signals: list[dict]) -> None:
    """Write all signals to PostgreSQL (full replace)."""
    import sqlalchemy as sa

    engine = get_pg_engine()
    ensure_pg_schema()

    with engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE TABLE cached_signals"))
        if signals:
            df = pd.DataFrame(signals)
            df["cached_at"] = datetime.now(UTC).isoformat()
            df.to_sql("cached_signals", engine, if_exists="append", index=False)


def write_to_redis(signals: list[dict]) -> None:
    """Write all signals to Redis as hot cache."""
    r = get_redis_client()
    pipe = r.pipeline()

    # Clear old cache
    pipe.delete("signals:all")
    pipe.delete("signals:buys")
    pipe.delete("signals:avoids")
    pipe.delete("signals:by_symbol")

    buys = [s for s in signals if s.get("signal_type") == "dz_hi_up"]
    avoids = [s for s in signals if s.get("signal_type") == "dz_hi_dn"]

    # Store as JSON
    pipe.set("signals:all", json.dumps(signals, default=str), ex=REDIS_TTL)
    pipe.set("signals:buys", json.dumps(buys, default=str), ex=REDIS_TTL)
    pipe.set("signals:avoids", json.dumps(avoids, default=str), ex=REDIS_TTL)
    pipe.set("signals:date", signals[0]["signal_date"] if signals else "", ex=REDIS_TTL)
    pipe.set("signals:count", str(len(signals)), ex=REDIS_TTL)

    # Store per-symbol lookup
    for s in signals:
        pipe.hset("signals:by_symbol", s["symbol"], json.dumps(s, default=str))
    pipe.expire("signals:by_symbol", REDIS_TTL)

    pipe.execute()


def warm_redis_from_pg() -> int:
    """Refresh Redis cache from PostgreSQL (fast, no parquet scan)."""

    engine = get_pg_engine()

    df = pd.read_sql("SELECT * FROM cached_signals", engine)
    if df.empty:
        return 0

    signals = df.to_dict(orient="records")
    write_to_redis(signals)
    return len(signals)


def main() -> int:
    parser = argparse.ArgumentParser(description="Cache delivery signals")
    parser.add_argument("--warm-redis", action="store_true",
                        help="Only refresh Redis from PostgreSQL (fast)")
    parser.parse_args()

    if warm_redis_from_pg.__code__.co_argcount == 0:
        pass  # always available

    args = sys.argv[1:]
    if "--warm-redis" in args:
        t0 = time.time()
        count = warm_redis_from_pg()
        print(json.dumps({"action": "warm_redis", "symbols": count, "time": f"{time.time()-t0:.1f}s"}))
        return 0

    settings = load_settings()
    nse_dir = settings.normalized_dir / "delivery" / "NSE"
    bse_dir = settings.normalized_dir / "delivery" / "BSE"

    t0 = time.time()
    signals = []

    if nse_dir.exists():
        for p in sorted(nse_dir.glob("*.parquet")):
            sig = compute_signal_for_stock(p, p.stem, "NSE")
            if sig:
                signals.append(sig)

    if bse_dir.exists():
        for p in sorted(bse_dir.glob("*.parquet")):
            sig = compute_signal_for_stock(p, p.stem, "BSE")
            if sig:
                signals.append(sig)

    elapsed_scan = time.time() - t0

    if signals:
        write_to_postgres(signals)
        write_to_redis(signals)

    elapsed_total = time.time() - t0
    buys = sum(1 for s in signals if s.get("signal_type") == "dz_hi_up")
    avoids = sum(1 for s in signals if s.get("signal_type") == "dz_hi_dn")

    print(json.dumps({
        "total_stocks": len(signals),
        "buys": buys,
        "avoids": avoids,
        "scan_time": f"{elapsed_scan:.1f}s",
        "total_time": f"{elapsed_total:.1f}s",
        "store": "postgresql+redis",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
