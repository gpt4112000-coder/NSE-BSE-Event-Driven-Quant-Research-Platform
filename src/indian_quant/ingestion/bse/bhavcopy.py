"""BSE UDiFF bhavcopy ingestion (bars-only).

Uses the same UDiFF schema BSE adopted alongside NSE:
    https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip

NOTE: BSE's CDN aggressively blocks datacenter IPs (serves an HTML block
page with HTTP 200). ``fetch_cm_zip`` detects this and raises
``SourceBlockedError`` rather than misparsing HTML as market data. From
residential/allowlisted networks the fetch works unchanged.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import UTC, date, datetime

import httpx

from indian_quant.schemas import (
    AdjustmentStatus,
    Exchange,
    MarketBar,
    QualityStatus,
    Segment,
    Timeframe,
    make_instrument_id,
)
from indian_quant.storage.raw_store import RawStore

CM_URL = "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{yyyymmdd}_F_0000.csv.zip"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://www.bseindia.com/markets/equity/EQMarket.html",
    "Accept": "*/*",
}


class SourceBlockedError(RuntimeError):
    """Raised when an upstream serves an anti-bot page instead of data."""


class BseBhavcopyIngester:
    source = "BSE"

    def __init__(
        self,
        raw_store: RawStore,
        *,
        timeout: float = 60.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.raw_store = raw_store
        self.timeout = timeout
        self._http = http_client or httpx.Client(timeout=timeout)

    def fetch_cm_zip(self, day: date) -> tuple[bytes | None, str]:
        yyyymmdd = day.strftime("%Y%m%d")
        resp = self._http.get(
            CM_URL.format(yyyymmdd=yyyymmdd), headers=HEADERS, follow_redirects=True,
        )
        if resp.status_code in (404, 403):
            return None, f"unavailable:{resp.status_code}"
        resp.raise_for_status()
        if self.is_block_page(resp.content):
            raise SourceBlockedError(
                f"BSE served an HTML block page instead of the bhavcopy for {day}; "
                "datacenter IPs are commonly blocked - retry from another network"
            )
        _, digest = self.raw_store.save(
            source="bse",
            tool="bhavcopy_cm_udiff",
            payload=resp.content,
            ext="zip",
            request_meta={"date": day.isoformat(), "url": str(resp.url)},
        )
        return resp.content, digest

    @staticmethod
    def is_block_page(payload: bytes) -> bool:
        """Detect BSE's anti-bot HTML page served with HTTP 200."""
        return payload[:512].lstrip().startswith(b"<")

    def parse_cm_zip(
        self,
        payload: bytes,
        day: date,
        *,
        symbols: set[str] | None = None,
        series: set[str] | None = None,
    ) -> list[MarketBar]:
        wanted_series = series or {"EQ"}
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            reader = csv.DictReader(io.StringIO(zf.read(name).decode("utf-8-sig")))
            bars: list[MarketBar] = []
            for row in reader:
                cleaned = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
                scry = cleaned.get("SctySrs", "")
                if scry not in wanted_series:
                    continue
                symbol = cleaned.get("TckrSymb", "")
                if not symbol or (symbols and symbol.upper() not in symbols):
                    continue
                try:
                    o = float(cleaned["OpnPric"])
                    h = float(cleaned["HghPric"])
                    low = float(cleaned["LwPric"])
                    c = float(cleaned["ClsPric"])
                    vol = float(cleaned.get("TtlTradgVol") or 0)
                except (KeyError, ValueError, TypeError):
                    continue
                ts_raw = cleaned.get("TradDt") or day.isoformat()
                try:
                    ts = datetime.fromisoformat(ts_raw).replace(tzinfo=UTC)
                except ValueError:
                    ts = datetime(day.year, day.month, day.day, tzinfo=UTC)
                bars.append(
                    MarketBar(
                        instrument_id=make_instrument_id(Exchange.BSE, Segment.EQ, symbol.upper()),
                        exchange="BSE",
                        timestamp=ts,
                        timeframe=Timeframe.DAY,
                        open=o,
                        high=h,
                        low=low,
                        close=c,
                        volume=vol,
                        source=self.source,
                        source_timestamp=ts,
                        ingestion_timestamp=datetime.now(UTC),
                        adjustment_status=AdjustmentStatus.UNADJUSTED,
                        quality_status=QualityStatus.RAW,
                    )
                )
            return bars
