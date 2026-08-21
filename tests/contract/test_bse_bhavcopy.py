"""BSE bhavcopy ingester tests (schema-exact synthetic fixture; live BSE is
IP-blocked from this environment, verified 2026-08)."""

import io
import zipfile
from datetime import date

import httpx
import pytest

from indian_quant.ingestion.bse import BseBhavcopyIngester, SourceBlockedError
from indian_quant.storage import RawStore

UDIFF_HEADER = (
    "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,"
    "OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol\n"
)
UDIFF_ROWS = (
    "2026-08-18,2026-08-18,CM,BSE,STK,500325,INE002A01018,RELIANCE,EQ,"
    "1305.00,1330.00,1300.10,1321.50,8500000\n"
    "2026-08-18,2026-08-18,CM,BSE,STK,500326,INE99999999,OTHERS,EQ,"
    "50.00,52.00,49.00,51.00,100000\n"
)


def make_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("BhavCopy_BSE_CM_0_0_0_20260818_F_0000.CSV", UDIFF_HEADER + UDIFF_ROWS)
    return buf.getvalue()


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(scope="module")
def ingester(tmp_path_factory):
    return BseBhavcopyIngester(RawStore(tmp_path_factory.mktemp("raw")))


class TestBseBhavcopy:
    def test_parse_udiff(self, ingester):
        bars = ingester.parse_cm_zip(make_zip_bytes(), date(2026, 8, 18), symbols={"RELIANCE"})
        assert len(bars) == 1
        bar = bars[0]
        assert bar.instrument_id == "BSE_EQ|RELIANCE"
        assert bar.exchange == "BSE"
        assert bar.close == pytest.approx(1321.5)
        assert bar.volume == pytest.approx(8_500_000)

    def test_series_filter(self, ingester):
        payload = make_zip_bytes()
        eq = ingester.parse_cm_zip(payload, date(2026, 8, 18))
        assert len(eq) == 2
        only_eq = ingester.parse_cm_zip(payload, date(2026, 8, 18), series={"XX"})
        assert only_eq == []

    def test_block_page_raises_never_parses(self, tmp_path):
        html = b"<!DOCTYPE html><html><body>blocked</body></html>"
        client = make_client(lambda request: httpx.Response(200, content=html))
        guarded = BseBhavcopyIngester(RawStore(tmp_path), http_client=client)
        with pytest.raises(SourceBlockedError):
            guarded.fetch_cm_zip(date(2026, 8, 18))

    def test_successful_fetch_persists_raw(self, tmp_path):
        client = make_client(lambda request: httpx.Response(200, content=make_zip_bytes()))
        store = RawStore(tmp_path / "raw")
        guarded = BseBhavcopyIngester(store, http_client=client)
        payload, digest = guarded.fetch_cm_zip(date(2026, 8, 18))
        assert payload == make_zip_bytes()
        assert len(digest) == 64
        stored = list((tmp_path / "raw" / "bse" / "bhavcopy_cm_udiff").rglob("*.zip"))
        assert len(stored) == 1

    def test_404_returns_none(self, tmp_path):
        client = make_client(lambda request: httpx.Response(404, text="nope"))
        guarded = BseBhavcopyIngester(RawStore(tmp_path), http_client=client)
        payload, digest = guarded.fetch_cm_zip(date(2026, 8, 18))
        assert payload is None and digest == "unavailable:404"
