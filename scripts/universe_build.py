"""Build the research universe registry from exchange evidence.

Primary source: recent NSE CM UDiFF bhavcopies already sitting in the raw
store - every traded symbol, its series (EQ/SM/ST/...) and ISIN. This is
the complete tradable universe and cannot be bot-blocked because it rides
the same CDN as ingestion.

Optional enrichment: MCP index/SME lists when reachable.

Output:
    data/universe/registry.json   canonical registry
    + instruments registered into the metadata store
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indian_quant.config import load_settings
from indian_quant.schemas import Exchange, InstrumentIdentity, SecurityType, Segment
from indian_quant.storage import MetadataStore

SERIES_SEGMENT = {"EQ": "EQ", "BE": "EQ", "BZ": "EQ", "SM": "SME", "ST": "SME"}


def scan_from_bhavcopies(settings, lookback_files: int = 5) -> dict[str, dict]:
    """Latest series+ISIN per symbol across the newest N CM bhavcopy zips."""
    raw_dir = settings.data_root / "raw" / "nse" / "bhavcopy_cm_udiff"
    zips = sorted(raw_dir.rglob("*.zip"), key=lambda p: p.stat().st_mtime,
                  reverse=True)[:lookback_files]
    universe: dict[str, dict] = {}
    scanned = 0
    for zp in zips:
        try:
            with zipfile.ZipFile(zp) as zf:
                name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
                reader = csv.DictReader(io.StringIO(zf.read(name).decode("utf-8-sig")))
                for row in reader:
                    symbol = (row.get("TckrSymb") or "").strip().upper()
                    series = (row.get("SctySrs") or "").strip()
                    segment = SERIES_SEGMENT.get(series)
                    if not symbol or not segment:
                        continue
                    entry = universe.setdefault(symbol, {
                        "symbol": symbol,
                        "segment": segment,
                        "series": series,
                        "isin": (row.get("ISIN") or "").strip() or None,
                        "source": f"bhavcopy:{zp.parent.name}",
                    })
                    # keep the freshest classification (files sorted newest first)
                    if zp == zips[0]:
                        entry["segment"] = segment
                        entry["series"] = series
        except (OSError, KeyError, zipfile.BadZipFile):
            continue
        scanned += 1
    print(f"scanned {scanned} bhavcopy files")
    return universe


def enrich_via_mcp(settings, universe: dict[str, dict]) -> None:
    """Best-effort index/SME list enrichment; ignored when NSE blocks."""
    try:
        from indian_quant.ingestion import NseBseMcpClient

        client = NseBseMcpClient(
            settings.mcp.base_url,
            timeout=settings.mcp.timeout_seconds,
            max_retries=settings.mcp.max_retries,
        )
        for index_name, cap_bucket in (("NIFTY 500", "large+mid"),
                                       ("NIFTY SMALLCAP 250", "small")):
            try:
                entries = client.call_tool("nse_list_stocks_by_index",
                                           {"index": index_name})
                records = entries if isinstance(entries, list) else (
                    entries.get("data") if isinstance(entries, dict) else []) or []
                hit = 0
                for entry in records:
                    if not isinstance(entry, dict):
                        continue
                    sym = str(entry.get("symbol") or "").strip().upper()
                    if sym in universe:
                        universe[sym]["cap_bucket"] = cap_bucket
                        hit += 1
                print(f"enriched {hit} symbols <- {index_name}")
            except Exception as exc:
                print(f"{index_name} enrichment skipped ({str(exc)[:80]})")
    except Exception as exc:
        print(f"MCP enrichment unavailable ({str(exc)[:80]})")


def register_instruments(settings, universe: dict[str, dict]) -> int:
    metadata = MetadataStore(settings.storage.metadata_dsn)
    count = 0
    for item in universe.values():
        segment = Segment.SME if item["segment"] == "SME" else Segment.EQ
        identity = InstrumentIdentity(
            instrument_id=f"NSE_{segment.value}|{item['symbol']}",
            exchange=Exchange.NSE,
            segment=segment,
            symbol=item["symbol"],
            isin=item.get("isin") or None,
            security_type=SecurityType.EQUITY,
        )
        metadata.register_instrument({
            "instrument_id": identity.instrument_id,
            "exchange": identity.exchange.value,
            "segment": identity.segment.value,
            "symbol": identity.symbol,
            "isin": identity.isin,
            "security_type": identity.security_type.value,
            "lot_size": 1,
            "tick_size": 0.05,
            "nautilus_instrument_id": identity.nautilus_instrument_id,
        })
        count += 1
    metadata.close()
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Build universe registry")
    parser.add_argument("--lookback-files", type=int, default=5)
    parser.add_argument("--no-mcp", action="store_true")
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    settings = load_settings(args.config)
    universe = scan_from_bhavcopies(settings, args.lookback_files)
    if not universe:
        print("no bhavcopy raw files found - run scripts/ingest.py first")
        return 1

    if not args.no_mcp:
        enrich_via_mcp(settings, universe)

    counts = {
        "total": len(universe),
        "eq": sum(1 for u in universe.values() if u["segment"] == "EQ"),
        "sme": sum(1 for u in universe.values() if u["segment"] == "SME"),
        "with_isin": sum(1 for u in universe.values() if u.get("isin")),
    }

    out_dir = settings.data_root / "universe"
    out_dir.mkdir(parents=True, exist_ok=True)
    registry = {
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").UTC).isoformat(),
        "counts": counts,
        "symbols": universe,
    }
    out_file = out_dir / "registry.json"
    out_file.write_text(json.dumps(registry, indent=2))

    registered = register_instruments(settings, universe)
    print(json.dumps({
        "registry_file": str(out_file),
        "counts": counts,
        "instruments_registered": registered,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
