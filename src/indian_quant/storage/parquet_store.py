"""Typed parquet storage for normalized and validated datasets.

Layout:
    {root}/{layer}/{dataset}/{exchange}/{symbol}.parquet

Writes are schema-enforced against the canonical contracts; reads return
pandas DataFrames with the same column order.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from indian_quant.schemas import MarketBar, bars_to_frame

Layer = Literal["normalized", "validated"]

BAR_ARROW_SCHEMA = pa.schema(
    [
        ("instrument_id", pa.string()),
        ("exchange", pa.string()),
        ("timestamp", pa.timestamp("ns", tz="UTC")),
        ("timeframe", pa.string()),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.float64()),
        ("open_interest", pa.float64()),
        ("source", pa.string()),
        ("source_timestamp", pa.timestamp("ns", tz="UTC")),
        ("ingestion_timestamp", pa.timestamp("ns", tz="UTC")),
        ("raw_hash", pa.string()),
        ("adjustment_status", pa.string()),
        ("quality_status", pa.string()),
    ]
)


class ParquetStore:
    def __init__(self, root: Path | str, compression: str = "zstd") -> None:
        self.root = Path(root)
        self.compression = compression

    def _path_for(self, layer: str, dataset: str, exchange: str, symbol: str) -> Path:
        safe_symbol = symbol.replace("|", "_").replace("/", "-")
        return self.root / layer / dataset / exchange.upper() / f"{safe_symbol}.parquet"

    def write_bars(
        self,
        bars: list[MarketBar],
        *,
        layer: Layer = "normalized",
    ) -> list[Path]:
        if not bars:
            return []
        df = bars_to_frame(bars)
        written: list[Path] = []
        for (instrument_id, timeframe), group in df.groupby(["instrument_id", "timeframe"]):
            exchange = str(group["exchange"].iloc[0]).upper()
            symbol = instrument_id.split("|")[-1]
            path = self._path_for(layer, f"bars_{timeframe}", exchange, symbol)
            path.parent.mkdir(parents=True, exist_ok=True)
            table = self._conform(group)
            pq.write_table(table, path, compression=self.compression)
            written.append(path)
        return written

    def read_bars(
        self,
        *,
        layer: Layer = "validated",
        exchange: str,
        symbol: str,
        timeframe: str = "1d",
    ) -> pd.DataFrame:
        path = self._path_for(layer, f"bars_{timeframe}", exchange, symbol)
        if not path.exists():
            raise FileNotFoundError(f"no bar dataset at {path}")
        return pq.read_table(path).to_pandas()

    def write_frame(
        self,
        df: pd.DataFrame,
        *,
        layer: Layer,
        dataset: str,
        exchange: str,
        name: str,
    ) -> Path:
        path = self._path_for(layer, dataset, exchange, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path,
                       compression=self.compression)
        return path

    def read_frame(self, *, layer: Layer, dataset: str, exchange: str, name: str) -> pd.DataFrame:
        path = self._path_for(layer, dataset, exchange, name)
        if not path.exists():
            raise FileNotFoundError(f"no dataset at {path}")
        return pq.read_table(path).to_pandas()

    def _conform(self, group: pd.DataFrame) -> pa.Table:
        for col in ("source_timestamp", "ingestion_timestamp"):
            if col in group.columns:
                group = group.copy()
                group[col] = pd.to_datetime(group[col], utc=True, errors="coerce")
        for col in BAR_ARROW_SCHEMA.names:
            if col not in group.columns:
                group[col] = None
        group = group[BAR_ARROW_SCHEMA.names]
        return pa.Table.from_pandas(group, schema=BAR_ARROW_SCHEMA, preserve_index=False)
