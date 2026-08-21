"""Symbol mapping between canonical ids, NautilusTrader and Upstox."""

from __future__ import annotations

import csv
import gzip
from dataclasses import dataclass, field
from pathlib import Path

from indian_quant.schemas import InstrumentIdentity


@dataclass(frozen=True)
class UpstoxInstrument:
    instrument_key: str
    trading_symbol: str
    exchange: str
    segment: str
    isin: str | None
    instrument_type: str
    expiry: str | None = None
    strike: float | None = None
    option_type: str | None = None


@dataclass
class SymbolMapper:
    """Bidirectional mapping across canonical / NSE / BSE / Nautilus / Upstox."""

    _by_canonical: dict[str, InstrumentIdentity] = field(default_factory=dict)
    _by_isin: dict[str, InstrumentIdentity] = field(default_factory=dict)
    _upstox_by_key: dict[str, UpstoxInstrument] = field(default_factory=dict)
    _upstox_by_symbol: dict[tuple[str, str], list[UpstoxInstrument]] = field(default_factory=dict)

    def register(self, identity: InstrumentIdentity) -> None:
        self._by_canonical[identity.instrument_id] = identity
        if identity.isin:
            self._by_isin[identity.isin] = identity

    def resolve(self, instrument_id: str) -> InstrumentIdentity:
        if instrument_id not in self._by_canonical:
            raise KeyError(f"unregistered instrument: {instrument_id}")
        return self._by_canonical[instrument_id]

    def by_isin(self, isin: str) -> InstrumentIdentity | None:
        return self._by_isin.get(isin.upper())

    @staticmethod
    def canonical_to_nautilus(instrument_id: str) -> str:
        try:
            from indian_quant.schemas import parse_instrument_id

            _, segment, local = parse_instrument_id(instrument_id)
        except ValueError:
            local = instrument_id.split("|")[-1]
            segment = "EQ"
        suffix = {"FO": ".NSEFO", "IDX": ".NSEIDX"}.get(segment, ".NSE")
        return f"{local.replace('|', '-').replace(' ', '_').upper()}{suffix}"

    def load_upstox_master(self, path: Path | str) -> int:
        """Load the Upstox instrument master CSV (optionally gzipped)."""
        opener = gzip.open if str(path).endswith(".gz") else open
        count = 0
        with opener(path, "rt", newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                inst = UpstoxInstrument(
                    instrument_key=row.get("instrument_key", ""),
                    trading_symbol=row.get("trading_symbol", row.get("symbol", "")),
                    exchange=row.get("exchange", ""),
                    segment=row.get("segment", ""),
                    isin=row.get("isin") or None,
                    instrument_type=row.get("instrument_type", ""),
                    expiry=row.get("expiry") or None,
                    strike=float(row["strike"]) if row.get("strike") else None,
                    option_type=row.get("option_type") or None,
                )
                self._upstox_by_key[inst.instrument_key] = inst
                key = (inst.exchange, inst.trading_symbol)
                self._upstox_by_symbol.setdefault(key, []).append(inst)
                count += 1
        return count

    def upstox_key_for(self, identity: InstrumentIdentity) -> str | None:
        """Best-effort mapping to an Upstox instrument_key for feed subscriptions."""
        if identity.isin:
            for inst in self._upstox_by_key.values():
                if inst.isin == identity.isin and inst.segment == "EQ":
                    return inst.instrument_key
        candidates = self._upstox_by_symbol.get(("NSE_EQ", identity.symbol), [])
        candidates += self._upstox_by_symbol.get(("NSE_FO", identity.symbol), [])
        return candidates[0].instrument_key if candidates else None


def default_mapper() -> SymbolMapper:
    return SymbolMapper()
