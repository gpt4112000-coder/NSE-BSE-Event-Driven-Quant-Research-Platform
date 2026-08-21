"""Export canonical pydantic contracts as JSON Schema files into schemas/.

Usage:
    python scripts/export_schemas.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indian_quant.schemas import (
    Announcement,
    CorporateAction,
    InstrumentIdentity,
    MarketBar,
    OptionInstrument,
    OptionQuote,
)

CONTRACTS = {
    "instrument.json": InstrumentIdentity,
    "option_instrument.json": OptionInstrument,
    "market_bar.json": MarketBar,
    "option_quote.json": OptionQuote,
    "corporate_action.json": CorporateAction,
    "announcement.json": Announcement,
}


def main() -> int:
    out_dir = Path(__file__).resolve().parents[1] / "schemas"
    out_dir.mkdir(exist_ok=True)
    for name, model in CONTRACTS.items():
        schema = model.model_json_schema()
        (out_dir / name).write_text(json.dumps(schema, indent=2, sort_keys=True))
        print(f"wrote schemas/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
