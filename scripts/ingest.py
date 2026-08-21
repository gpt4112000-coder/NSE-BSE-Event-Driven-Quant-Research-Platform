"""Ingest NSE data via MCP: raw store -> normalized parquet.

Usage:
    python scripts/ingest.py --symbol RELIANCE --from 2024-01-01 --to 2025-01-01
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indian_quant.config import load_settings
from indian_quant.ingestion import NseBseMcpClient, NseIngestionService
from indian_quant.normalization import deduplicate_bars
from indian_quant.storage import MetadataStore, ParquetStore, RawStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest NSE historical data via MCP")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    settings = load_settings(args.config)
    client = NseBseMcpClient(
        settings.mcp.base_url,
        timeout=settings.mcp.timeout_seconds,
        max_retries=settings.mcp.max_retries,
    )
    service = NseIngestionService(
        client,
        RawStore(settings.data_root / "raw"),
        MetadataStore(settings.storage.metadata_dsn),
    )
    bars = service.equity_historical(
        args.symbol.upper(), date.fromisoformat(args.from_date), date.fromisoformat(args.to_date)
    )
    if not bars:
        print(f"no bars returned for {args.symbol}; is the MCP server running? (make mcp)")
        return 1

    unique = deduplicate_bars(bars)
    store = ParquetStore(settings.normalized_dir, settings.storage.parquet_compression)
    paths = store.write_bars(unique, layer="normalized")
    print(f"ingested {len(unique)} bars for {args.symbol.upper()} -> {paths[0].parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
