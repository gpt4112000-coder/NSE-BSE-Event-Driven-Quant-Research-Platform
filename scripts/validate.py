"""Run the quality suite over normalized bars -> validated layer + report.

Usage:
    python scripts/validate.py --symbol RELIANCE
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pyarrow.parquet as pq

from indian_quant.config import load_settings
from indian_quant.quality import run_quality_suite
from indian_quant.schemas import MarketBar, Timeframe
from indian_quant.storage import MetadataStore, ParquetStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate normalized bars")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--exchange", default="NSE")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    settings = load_settings(args.config)
    store = ParquetStore(settings.data_root, settings.storage.parquet_compression)
    df = store.read_bars(
        layer="normalized", exchange=args.exchange, symbol=args.symbol.upper(),
        timeframe=args.timeframe,
    )
    bars = [
        MarketBar(
            instrument_id=row.instrument_id,
            exchange=row.exchange,
            timestamp=row.timestamp.to_pydatetime(),
            timeframe=Timeframe(row.timeframe),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
            source=str(row.source),
            adjustment_status=row.adjustment_status,
            quality_status=row.quality_status,
        )
        for row in df.itertuples(index=False)
    ]
    report, unique = run_quality_suite(bars, dataset=f"{args.exchange}:{args.symbol}")
    metadata = MetadataStore(settings.storage.metadata_dsn)
    metadata.record_quality_report(dataset=report.dataset, report=report.to_dict())

    out_dir = settings.validated_dir / f"bars_{args.timeframe}" / args.exchange.upper()
    out_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        store._conform(__import__("pandas").DataFrame([b.model_dump() for b in unique])),
        out_dir / f"{args.symbol.upper()}.parquet",
        compression=settings.storage.parquet_compression,
    )
    print(json.dumps(report.to_dict(), indent=2)[:2000])
    print(f"validated {len(unique)} rows -> {out_dir / (args.symbol.upper() + '.parquet')}")
    return 0 if report.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
