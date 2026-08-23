"""Daily signal report: today's delivery-signal candidates across the universe.

Scans the latest delivery lake day, fires dz_hi_up / avoidance (dz_hi_dn)
signals, applies liquidity + price filters, sizes positions against
configured risk capital, and prints a morning sheet.

Usage:
    python scripts/daily_signals.py [--capital 25000] [--risk-pct 1]
                                    [--price-max 500] [--top 10]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from indian_quant.config import load_settings
from indian_quant.features.delivery import add_features, prepare_frame


def scan_symbol(path: Path) -> dict | None:
    try:
        raw = pd.read_parquet(path)
    except Exception:
        return None
    frame = prepare_frame(raw, min_rows=40)
    if frame is None or "volume" not in frame.columns:
        return None
    frame = add_features(frame)
    last = frame.iloc[-1]
    prev = frame.iloc[-2] if len(frame) > 1 else last

    notional = float(last["close"] * last["volume"])
    return {
        "symbol": str(last["symbol"]),
        "segment": str(last["segment"]),
        "close": round(float(last["close"]), 2),
        "ret_1d_pct": round(float(last["ret_1d"]) * 100, 2) if pd.notna(last["ret_1d"]) else None,
        "deliv_pct": round(float(last["deliv_pct"]), 1) if pd.notna(last["deliv_pct"]) else None,
        "deliv_z": round(float(last["deliv_z"]), 2) if pd.notna(last["deliv_z"]) else None,
        "vol_z": round(float(last["vol_z"]), 2) if pd.notna(last.get("vol_z")) else None,
        "median_turnover": round(notional, 0),
        "_dz_prev": None if pd.isna(prev.get("deliv_z")) else float(prev["deliv_z"]),
        "_ret_prev": None if pd.isna(prev.get("ret_1d")) else float(prev["ret_1d"]),
        "_date": str(last["date"].date()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily delivery-signal report")
    parser.add_argument("--capital", type=float, default=25_000.0)
    parser.add_argument("--risk-pct", type=float, default=1.0,
                        help="max account risk per position, percent")
    parser.add_argument("--price-max", type=float, default=500.0)
    parser.add_argument("--price-min", type=float, default=20.0)
    parser.add_argument("--min-turnover", type=float, default=10_000_000,
                        help="min median daily turnover in rupees (liquidity floor)")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    settings = load_settings(None if len(sys.argv) < 2 else None)
    dl_dir = settings.normalized_dir / "delivery" / "NSE"

    rows: list[dict] = []
    latest_date = ""
    for path in sorted(dl_dir.glob("*.parquet")):
        info = scan_symbol(path)
        if info is None:
            continue
        latest_date = max(latest_date, info["_date"])
        rows.append(info)

    df = pd.DataFrame(rows)
    df = df[df["_date"] == latest_date]
    liquid = df[df["median_turnover"] >= args.min_turnover]

    buys = liquid[
        (liquid["deliv_z"] >= 2)
        & (liquid["ret_1d_pct"] >= 0.5)
        & (liquid["close"] <= args.price_max)
        & (liquid["close"] >= args.price_min)
    ].sort_values("deliv_z", ascending=False).head(args.top)

    avoid = liquid[
        (liquid["deliv_z"] >= 2)
        & (liquid["ret_1d_pct"] <= -0.5)
    ].sort_values("deliv_z", ascending=False).head(args.top)

    risk_rupees = args.capital * args.risk_pct / 100.0

    def size(row) -> int:
        stop_dist = row["close"] * 0.07
        if stop_dist <= 0:
            return 0
        by_risk = int(risk_rupees // stop_dist)
        by_capital = int((args.capital * 0.3) // (row["close"] * 1))
        return max(0, min(by_risk, by_capital))

    print("=" * 74)
    print(f" DAILY DELIVERY SIGNALS · data through {latest_date}")
    print(f" capital ₹{args.capital:,.0f} | risk/pos {args.risk_pct}% = ₹{risk_rupees:,.0f} "
          f"| price band {args.price_min}-{args.price_max}")
    print("=" * 74)

    if buys.empty:
        print("\n(no BUY candidates today - discipline is also a position)")
    else:
        print("\n🟢 ACCUMULATION CANDIDATES (delivery z≥2 on up-move) — "
              "reference hold ~3-10d\n")
        for _, r in buys.iterrows():
            qty = size(r)
            print(f"  {r['symbol']:<14} {r['segment']:<4} close ₹{r['close']:>9,.2f} "
                  f"| deliv {r['deliv_pct']}% (z {r['deliv_z']}) "
                  f"| vol z {r['vol_z']} | qty {qty}")

    if not avoid.empty:
        print("\n🔴 AVOID / EXIT-WATCH (distribution: delivery z≥2 on down-move)\n")
        for _, r in avoid.iterrows():
            print(f"  {r['symbol']:<14} {r['segment']:<4} close ₹{r['close']:>9,.2f} "
                  f"| deliv {r['deliv_pct']}% (z {r['deliv_z']})")

    print("\nNotes: signals are research output, not advice. Entry via limit orders.")
    print("Re-run after 18:30 IST for same-day delivery data refresh.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
