"""Sync validated bars into the Nautilus ParquetDataCatalog.

Usage:
    python scripts/sync_catalog.py --symbol RELIANCE
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indian_quant.config import load_settings
from indian_quant.nautilus.data.catalog import sync_validated_to_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync validated data to Nautilus catalog")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--exchange", default="NSE")
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    settings = load_settings(args.config)
    written = sync_validated_to_catalog(
        validated_dir=settings.validated_dir,
        catalog_path=settings.catalog_dir,
        exchange=args.exchange,
        symbols=[args.symbol.upper()] if args.symbol else None,
        timeframe=args.timeframe,
    )
    if not written:
        print("nothing synced; run scripts/validate.py first")
        return 1
    for inst_id, bt in written.items():
        print(f"{inst_id} -> {bt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
