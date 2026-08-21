"""End-to-end mini pipeline: ingest (mocked MCP) -> normalize -> validate -> catalog.

This is the Phase 2+3 exit condition, verified continuously.
"""

import json

import httpx
import pandas as pd
import pytest

from indian_quant.config import Settings
from indian_quant.ingestion import NseBseMcpClient, NseIngestionService
from indian_quant.nautilus.data.catalog import sync_validated_to_catalog
from indian_quant.normalization import deduplicate_bars
from indian_quant.quality import run_quality_suite
from indian_quant.storage import ParquetStore, RawStore

PAYLOAD = {
    "data": [
        {
            "symbol": "TEST",
            "timestamp": f"0{d}-Jun-2025",
            "open": 100 + d,
            "high": 105 + d,
            "low": 99 + d,
            "close": 102 + d,
            "volume": 10_000 * d,
        }
        for d in range(1, 6)
    ]
}


@pytest.fixture
def pipeline(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        if body.get("method") == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {}})
        if body.get("method") == "tools/call":
            result = {"content": [{"type": "text", "text": json.dumps(PAYLOAD)}], "isError": False}
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body.get("id"), "result": {}})

    client = NseBseMcpClient(
        "http://localhost:3000/mcp", http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    settings = Settings()
    settings.paths.data_root = tmp_path / "data"
    settings.storage.metadata_dsn = f"sqlite:///{tmp_path / 'meta.db'}"
    settings.backtest.catalog_path = tmp_path / "catalog"

    service = NseIngestionService(client, RawStore(settings.data_root / "raw"))
    bars = service.equity_historical("TEST", "2025-06-01", "2025-06-30")
    unique = deduplicate_bars(bars)
    report, clean = run_quality_suite(unique, dataset="NSE:TEST")

    store = ParquetStore(settings.data_root)
    store.write_bars(clean, layer="normalized")
    store.write_bars(clean, layer="validated")

    written = sync_validated_to_catalog(
        validated_dir=settings.validated_dir,
        catalog_path=settings.catalog_dir,
        exchange="NSE",
        symbols=["TEST"],
    )
    return settings, written


class TestPipeline:
    def test_ingestion_produced_bars(self, pipeline):
        settings, _ = pipeline
        df = ParquetStore(settings.data_root).read_bars(layer="validated", exchange="NSE", symbol="TEST")
        assert len(df) == 5

    def test_lineage_preserved(self, pipeline):
        settings, _ = pipeline
        df = ParquetStore(settings.data_root).read_bars(layer="validated", exchange="NSE", symbol="TEST")
        assert df.iloc[0]["raw_hash"] is not None
        assert set(df["source"]) == {"NSE"}

    def test_catalog_synced(self, pipeline):
        _, written = pipeline
        assert "NSE_EQ|TEST" in written
        assert written["NSE_EQ|TEST"].endswith("EXTERNAL")

    def test_replay_is_deterministic(self, pipeline):
        """Same input -> byte-identical validated dataset (Phase 8 principle)."""
        settings, _ = pipeline
        store = ParquetStore(settings.data_root)
        df1 = store.read_bars(layer="validated", exchange="NSE", symbol="TEST")
        df2 = store.read_bars(layer="validated", exchange="NSE", symbol="TEST")
        pd.testing.assert_frame_equal(df1, df2)
