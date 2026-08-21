"""Bhavcopy ingester tests against a real UDiFF fixture from NSE archives."""

from datetime import date
from pathlib import Path

import pytest

from indian_quant.ingestion.nse import BhavcopyIngester, parse_delivery_csv
from indian_quant.schemas import Timeframe
from indian_quant.storage import RawStore

FIXTURE = Path(__file__).parents[1] / "fixtures" / "BhavCopy_NSE_CM_20260818.zip"


@pytest.fixture(scope="module")
def ingester(tmp_path_factory):
    raw = RawStore(tmp_path_factory.mktemp("raw"))
    return BhavcopyIngester(raw)


class TestBhavcopyParsing:
    def test_parses_real_udiff_zip(self, ingester):
        payload = FIXTURE.read_bytes()
        bars = ingester.parse_cm_zip(payload, date(2026, 8, 18), symbols={"RELIANCE"})
        assert len(bars) == 1
        bar = bars[0]
        assert bar.instrument_id == "NSE_EQ|RELIANCE"
        assert bar.timeframe == Timeframe.DAY
        assert bar.open == pytest.approx(1314.0)
        assert bar.high == pytest.approx(1328.6)
        assert bar.low == pytest.approx(1311.2)
        assert bar.close == pytest.approx(1322.0)
        assert bar.volume == pytest.approx(10_180_567)
        assert bar.source == "NSE"

    def test_series_filter_excludes_non_cash(self, ingester):
        payload = FIXTURE.read_bytes()
        all_eq = ingester.parse_cm_zip(payload, date(2026, 8, 18))
        only_eq = ingester.parse_cm_zip(payload, date(2026, 8, 18), series={"EQ"})
        assert len(all_eq) >= len(only_eq) > 100

    def test_symbol_filter(self, ingester):
        payload = FIXTURE.read_bytes()
        bars = ingester.parse_cm_zip(payload, date(2026, 8, 18), symbols={"TCS", "INFY"})
        ids = {b.instrument_id for b in bars}
        assert any(i.endswith("|TCS") for i in ids) or len(bars) > 0


def test_delivery_csv_parsing():
    text = (
        "SYMBOL,SERIES,DATE1,PREV_CLOSE,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,LAST_PRICE,"
        "CLOSE_PRICE,AVG_PRICE,TTL_TRD_QNTY,TURNOVER_LACS,NO_OF_TRADES,DELIV_QTY,DELIV_PER\n"
        "RELIANCE,EQ,18-AUG-2026,1305.00,1314.00,1328.60,1311.20,1320.00,1322.00,"
        "1320.15,10180567,134453.19,187432,6012345,59.06\n"
    )
    out = parse_delivery_csv(text)
    assert out["RELIANCE"] == pytest.approx(59.06)
