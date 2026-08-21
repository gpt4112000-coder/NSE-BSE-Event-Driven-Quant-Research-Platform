"""Register a symbol lifecycle event (rename/suspension/delisting/migration).

Usage:
    python scripts/register_symbol_event.py --isin INE002A01018 --exchange NSE \
        --event RENAME --from OLD --to NEW --effective 2026-01-01
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indian_quant.config import load_settings
from indian_quant.storage import MetadataStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Register a symbol event")
    parser.add_argument("--isin", required=True)
    parser.add_argument("--exchange", required=True)
    parser.add_argument("--event", required=True,
                        choices=["RENAME", "SUSPENSION", "DELISTING", "SEGMENT_MIGRATION"])
    parser.add_argument("--effective", required=True, help="YYYY-MM-DD")
    parser.add_argument("--from", dest="from_symbol", default=None)
    parser.add_argument("--to", dest="to_symbol", default=None)
    parser.add_argument("--note", default=None)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    settings = load_settings(args.config)
    metadata = MetadataStore(settings.storage.metadata_dsn)
    event_id = metadata.record_symbol_event(
        isin=args.isin,
        exchange=args.exchange,
        event_type=args.event,
        effective_date=args.effective,
        from_symbol=args.from_symbol,
        to_symbol=args.to_symbol,
        note=args.note,
    )
    events = metadata.symbol_events_for_isin(args.isin)
    print(json.dumps({"recorded_event_id": event_id,
                      "events_for_isin": len(events)}, indent=2))
    metadata.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
