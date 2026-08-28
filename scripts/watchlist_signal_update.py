"""Update cached signals for all watchlisted stocks.

Called once during the daily update cycle after suggestion_manager record.
Reads all watchlist entries, computes delivery features, writes to watchlist_signals.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from indian_quant.config import load_settings
from indian_quant.features.delivery import add_features, prepare_frame, signal_mask
from indian_quant.web.watchlist_store import WatchlistStore


def main() -> int:
    settings = load_settings()
    db = Path(settings.storage.metadata_dsn.removeprefix("sqlite:///"))
    ws = WatchlistStore(db)

    import sqlite3 as _sq
    con = _sq.connect(str(db))
    rows = con.execute(
        "SELECT DISTINCT user_id FROM watchlists"
    ).fetchall()
    con.close()

    if not rows:
        print("no watchlists to update")
        ws.close()
        return 0

    dl_dir = settings.normalized_dir / "delivery" / "NSE"
    total = 0

    for (user_id,) in rows:
        stocks = ws.list_stocks(user_id)
        for stock in stocks:
            symbol = stock["symbol"]
            parquet = dl_dir / f"{symbol}.parquet"
            if not parquet.exists():
                continue

            try:
                raw = pd.read_parquet(parquet)
                if raw.empty:
                    continue
                frame = prepare_frame(raw, min_rows=min(20, len(raw)))
                if frame is None or frame.empty:
                    continue
                frame = add_features(frame)
                if frame.empty:
                    continue

                last = frame.iloc[-1]
                signals = signal_mask(frame)
                last_signal = bool(signals.iloc[-1]) if len(signals) > 0 else False

                signal_type = None
                if last_signal:
                    if pd.notna(last.get("deliv_z")) and last["deliv_z"] >= 2 and pd.notna(last.get("ret_1d")) and last["ret_1d"] >= 0.005:
                        signal_type = "dz_hi_up"
                    elif pd.notna(last.get("deliv_z")) and last["deliv_z"] >= 2 and pd.notna(last.get("ret_1d")) and last["ret_1d"] <= -0.005:
                        signal_type = "dz_hi_dn"

                close = float(last["close"])
                atr = float(last.get("atr_14", close * 0.03)) if pd.notna(last.get("atr_14")) else close * 0.03

                wl_id = ws.get_watchlist_id(user_id, symbol)
                if wl_id is None:
                    continue

                ws.save_signal(wl_id, user_id, symbol, {
                    "signal_date": str(pd.to_datetime(last["date"]).date()),
                    "signal_type": signal_type,
                    "close": close,
                    "deliv_pct": float(last["deliv_pct"]) if pd.notna(last.get("deliv_pct")) else None,
                    "deliv_z": float(last["deliv_z"]) if pd.notna(last.get("deliv_z")) else None,
                    "vol_z": float(last["vol_z"]) if pd.notna(last.get("vol_z")) else None,
                    "ret_1d": float(last["ret_1d"]) if pd.notna(last.get("ret_1d")) else None,
                    "rsi": float(last["rsi"]) if pd.notna(last.get("rsi")) else None,
                    "macd": float(last["macd"]) if pd.notna(last.get("macd")) else None,
                    "macd_signal": float(last["macd_signal"]) if pd.notna(last.get("macd_signal")) else None,
                    "sma_20": float(last["sma_20"]) if pd.notna(last.get("sma_20")) else None,
                    "sma_50": float(last["sma_50"]) if pd.notna(last.get("sma_50")) else None,
                    "atr_14": atr,
                    "entry_zone_low": round(close - atr * 0.5, 2),
                    "entry_zone_high": round(close, 2),
                    "stop_loss": round(close * 0.93, 2),
                    "target_price": round(close * 1.05, 2),
                })
                total += 1
            except Exception as exc:
                print(f"  {symbol}: {exc}")
                continue

    ws.close()
    print(f"watchlist signals updated: {total} stocks across {len(rows)} users")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
