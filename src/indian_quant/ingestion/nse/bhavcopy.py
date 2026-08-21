"""NSE UDiFF bhavcopy ingestion: exchange archives CDN -> canonical bars.

The NSE quote/chart APIs are aggressively bot-blocked; the public archives
CDN is not. This is therefore the primary historical-bars source, and it is
also the most research-grade one: full-exchange files with ISINs.

Sources:
    CM UDiFF:    https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip
    Delivery:    https://narchives.nseindia.com/products/content/sec_bhavdata_full_{DDMMYYYY}.csv
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import UTC, date, datetime
from typing import Any

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

CM_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{yyyymmdd}_F_0000.csv.zip"
DELIVERY_URL = "https://narchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"

CASH_SERIES = {"EQ", "BE", "BZ"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


class BhavcopyIngester:
    source = "NSE"

    def __init__(self, raw_store: RawStore, *, timeout: float = 60.0) -> None:
        self.raw_store = raw_store
        self.timeout = timeout

    def fetch_cm_zip(self, day: date) -> tuple[bytes | None, str]:
        """Download the CM bhavcopy zip for a trading day; persist raw bytes."""
        yyyymmdd = day.strftime("%Y%m%d")
        resp = httpx.get(
            CM_URL.format(yyyymmdd=yyyymmdd), headers=HEADERS,
            timeout=self.timeout, follow_redirects=True,
        )
        if resp.status_code == 404 or resp.status_code == 403:
            return None, f"unavailable:{resp.status_code}"
        resp.raise_for_status()
        _, digest = self.raw_store.save(
            source="nse",
            tool="bhavcopy_cm_udiff",
            payload=resp.content,
            ext="zip",
            request_meta={"date": day.isoformat(), "url": str(resp.url)},
        )
        return resp.content, digest

    def parse_cm_zip(
        self,
        payload: bytes,
        day: date,
        *,
        symbols: set[str] | None = None,
        series: set[str] | None = None,
    ) -> list[MarketBar]:
        """Parse a CM UDiFF zip into canonical daily bars."""
        wanted_series = series or CASH_SERIES
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            name = next(n for n in zf.namelist() if n.endswith(".csv"))
            reader = csv.DictReader(io.StringIO(zf.read(name).decode("utf-8-sig")))
            bars: list[MarketBar] = []
            for row in reader:
                if row.get("SctySrs") not in wanted_series:
                    continue
                symbol = (row.get("TckrSymb") or "").strip()
                if not symbol or (symbols and symbol.upper() not in symbols):
                    continue
                try:
                    o = float(row["OpnPric"])
                    h = float(row["HghPric"])
                    low = float(row["LwPric"])
                    c = float(row["ClsPric"])
                    vol = float(row.get("TtlTradgVol") or 0)
                except (KeyError, ValueError, TypeError):
                    continue
                ts = datetime.fromisoformat(str(row.get("TradDt") or day.isoformat())).replace(tzinfo=UTC)
                bars.append(
                    MarketBar(
                        instrument_id=make_instrument_id(Exchange.NSE, Segment.EQ, symbol.upper()),
                        exchange="NSE",
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

    def ingest_range(
        self,
        from_date: date,
        to_date: date,
        *,
        symbols: set[str] | None = None,
    ) -> list[MarketBar]:
        """Ingest every available trading day in [from_date, to_date]."""
        all_bars: list[MarketBar] = []
        cursor = from_date
        while cursor <= to_date:
            if cursor.weekday() < 5:
                payload, _ = self.fetch_cm_zip(cursor)
                if payload:
                    all_bars.extend(self.parse_cm_zip(payload, cursor, symbols=symbols))
                else:
                    print(f"  no bhavcopy for {cursor} (holiday/unlisted)")
            cursor = date.fromordinal(cursor.toordinal() + 1)
        return all_bars


def parse_delivery_csv(text: str) -> dict[str, float]:
    """Parse sec_bhavdata_full delivery CSV -> {symbol: delivery_pct}."""
    out: dict[str, float] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        cleaned = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        symbol = cleaned.get("SYMBOL", "")
        pct = cleaned.get("DELIV_PER", "")
        if symbol and pct not in ("", "-"):
            try:
                out[symbol] = float(pct)
            except ValueError:
                continue
    return out


def udiff_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if v not in ("", "-")}
