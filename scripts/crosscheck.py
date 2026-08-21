"""Cross-source verification: same instrument, independent files, matching closes.

Compares close prices for a symbol across source pairs present in the lake:

    nse_cm_vs_nse_delivery  - CM bhavcopy vs sec_bhavdata_full (available now)
    nse_cm_vs_bse_cm        - NSE vs BSE UDiFF (activates when BSE bars land)

Tolerance policy: drift > warning threshold flags a WARNING, > error
threshold flags an ERROR and fails the run.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from indian_quant.config import load_settings
from indian_quant.ingestion.nse import BhavcopyIngester, parse_delivery_csv
from indian_quant.storage import MetadataStore, RawStore


@dataclass
class CrosscheckReport:
    pair: str
    symbol: str
    n_compared: int
    n_warning: int
    n_error: int
    max_drift_pct: float
    details: list[dict]

    @property
    def passed(self) -> bool:
        return self.n_error == 0

    def to_dict(self) -> dict:
        return {
            "pair": self.pair,
            "symbol": self.symbol,
            "n_compared": self.n_compared,
            "n_warning": self.n_warning,
            "n_error": self.n_error,
            "max_drift_pct": round(self.max_drift_pct, 4),
            "passed": self.passed,
            "worst_days": sorted(
                self.details, key=lambda d: d["drift_pct"], reverse=True
            )[:5],
        }


def compare_series(
    left: pd.Series,
    right: pd.Series,
    *,
    pair: str,
    symbol: str,
    warn_pct: float,
    error_pct: float,
) -> CrosscheckReport:
    """Compare two date-indexed close series on their overlap."""
    common = left.index.intersection(right.index)
    details: list[dict] = []
    n_warn = n_err = 0
    max_drift = 0.0
    for day in common:
        lval = float(left.loc[day])
        rval = float(right.loc[day])
        if lval <= 0:
            continue
        drift_pct = abs(rval / lval - 1.0) * 100
        max_drift = max(max_drift, drift_pct)
        severity = None
        if drift_pct > error_pct:
            severity = "error"
            n_err += 1
        elif drift_pct > warn_pct:
            severity = "warning"
            n_warn += 1
        if severity:
            details.append({
                "date": str(day.date()) if hasattr(day, "date") else str(day),
                "left": lval,
                "right": rval,
                "drift_pct": round(drift_pct, 4),
                "severity": severity,
            })
    return CrosscheckReport(pair, symbol, len(common), n_warn, n_err, max_drift, details)


def load_delivery_closes(settings, symbol: str) -> pd.Series:
    store = RawStore(settings.data_root / "raw")
    ingester = BhavcopyIngester(store)
    closes: dict[date, float] = {}
    for meta_file in sorted((settings.data_root / "raw" / "nse" / "bhavcopy_delivery_sec").rglob("*.meta.json")):
        payload_path = meta_file.with_suffix("").with_suffix(".csv")
        if not payload_path.exists():
            continue
        text = payload_path.read_text()
        parsed = parse_delivery_csv(text)
        rec = parsed.get(symbol.upper())
        if not rec or "close" not in rec:
            continue
        meta = json.loads(meta_file.read_text())
        day_str = meta.get("request", {}).get("date")
        if not day_str:
            continue
        closes[date.fromisoformat(day_str)] = rec["close"]
    _ = ingester
    return pd.Series(closes).sort_index()


def fetch_missing_delivery_days(settings, symbol: str, days: list[date], limit: int = 8) -> int:
    """Fetch delivery files for recent validated dates that are not yet in raw store."""
    ingester = BhavcopyIngester(RawStore(settings.data_root / "raw"))
    have = {
        json.loads(m.read_text()).get("request", {}).get("date")
        for m in (settings.data_root / "raw" / "nse" / "bhavcopy_delivery_sec").rglob("*.meta.json")
    }
    fetched = 0
    for day in reversed(days):
        if fetched >= limit:
            break
        if day.isoformat() in have:
            continue
        _, digest = ingester.fetch_delivery_csv(day)
        if digest and not str(digest).startswith(("unavailable", "blocked")):
            fetched += 1
    return fetched


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-source close verification")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--warn-pct", type=float, default=0.1)
    parser.add_argument("--error-pct", type=float, default=0.5)
    parser.add_argument("--pair", choices=["auto", "nse_cm_vs_nse_delivery", "nse_cm_vs_bse_cm"],
                        default="auto")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    settings = load_settings(args.config)
    symbol = args.symbol.upper()

    from indian_quant.storage import ParquetStore

    store = ParquetStore(settings.data_root)
    try:
        df = store.read_bars(layer="validated", exchange="NSE", symbol=symbol)
    except FileNotFoundError:
        df = store.read_bars(layer="normalized", exchange="NSE", symbol=symbol)

    cm_closes = pd.Series(
        df["close"].values, index=pd.DatetimeIndex(pd.to_datetime(df["timestamp"], utc=True)).normalize()
    ).sort_index()
    trading_dates = [ts.date() for ts in cm_closes.index]

    reports: list[CrosscheckReport] = []

    want_delivery = args.pair in ("auto", "nse_cm_vs_nse_delivery")
    if want_delivery:
        fetch_missing_delivery_days(settings, symbol, trading_dates)
        delivery = load_delivery_closes(settings, symbol)
        if not delivery.empty:
            delivery.index = pd.DatetimeIndex(pd.to_datetime(pd.Series(delivery.index), utc=True)).normalize()
            reports.append(compare_series(
                cm_closes, delivery,
                pair="nse_cm_vs_nse_delivery", symbol=symbol,
                warn_pct=args.warn_pct, error_pct=args.error_pct,
            ))
        else:
            print("delivery source unavailable; skipping pair")

    want_bse = args.pair in ("auto", "nse_cm_vs_bse_cm")
    if want_bse:
        bse_dir = settings.data_root / "normalized" / "bars_1d" / "BSE"
        bse_path = bse_dir / f"{symbol}.parquet"
        if bse_path.exists():
            bdf = pd.read_parquet(bse_path)
            bse_closes = pd.Series(
                bdf["close"].values,
                index=pd.DatetimeIndex(pd.to_datetime(bdf["timestamp"], utc=True)).normalize(),
            ).sort_index()
            reports.append(compare_series(
                cm_closes, bse_closes,
                pair="nse_cm_vs_bse_cm", symbol=symbol,
                warn_pct=args.warn_pct, error_pct=args.error_pct,
            ))
        else:
            print("no BSE bars in lake; nse_cm_vs_bse_cm skipped")

    if not reports:
        print("no comparable sources available")
        return 1

    metadata = MetadataStore(settings.storage.metadata_dsn)
    exit_code = 0
    for report in reports:
        payload = report.to_dict()
        print(json.dumps(payload, indent=2))
        metadata.record_quality_report(dataset=f"crosscheck:{report.pair}:{symbol}", report=payload)
        if not report.passed:
            exit_code = 2
    metadata.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
