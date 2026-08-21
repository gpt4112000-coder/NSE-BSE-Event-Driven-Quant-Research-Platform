"""Canonical instrument identity contracts.

The canonical instrument_id format is ``{EXCHANGE}_{SEGMENT}|{LOCAL_ID}``:

* ``NSE_EQ|RELIANCE``          - NSE cash equity
* ``BSE_EQ|500325``            - BSE scrip (numeric code)
* ``NSE_FO|BANKNIFTY-2026-09-24-CE-52000``  - option contract
* ``NSE_FO|BANKNIFTY-2026-09-24-FUT``       - futures contract

This guarantees an NSE equity can never be confused with an NSE F&O
contract or a BSE scrip, regardless of what any upstream source calls it.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from indian_quant.schemas.enums import Exchange, OptionType, SecurityType, Segment
from indian_quant.schemas.lineage import Lineage

ID_SEPARATOR = "|"


def make_instrument_id(
    exchange: Exchange | str,
    segment: Segment | str,
    local_id: str,
) -> str:
    return f"{str(exchange).upper()}_{str(segment).upper()}{ID_SEPARATOR}{local_id}"


def parse_instrument_id(instrument_id: str) -> tuple[str, str, str]:
    head, _, local = instrument_id.partition(ID_SEPARATOR)
    if not head or not local or "_" not in head:
        raise ValueError(
            f"invalid canonical instrument_id: {instrument_id!r} "
            f"(expected EXCHANGE_SEGMENT|LOCAL_ID)"
        )
    exchange, _, segment = head.partition("_")
    return exchange, segment, local


def make_option_local_id(
    underlying: str,
    expiry: date,
    option_type: OptionType | str,
    strike: float,
) -> str:
    ot = str(option_type).upper()
    if ot not in ("CE", "PE"):
        raise ValueError(f"option_type must be CE or PE, got {option_type!r}")
    return f"{underlying.upper()}-{expiry.isoformat()}-{ot}-{strike:g}"


class InstrumentIdentity(BaseModel):
    """Exchange-agnostic identity of a tradable instrument."""

    model_config = ConfigDict(frozen=True)

    instrument_id: str
    exchange: Exchange
    segment: Segment
    symbol: str
    isin: str | None = None
    security_type: SecurityType = SecurityType.EQUITY
    currency: str = "INR"
    lot_size: int = 1
    tick_size: float = 0.05
    name: str | None = None
    expiry: date | None = None
    strike: float | None = None
    option_type: OptionType | None = None
    underlying: str | None = None
    lineage: Lineage | None = None

    @field_validator("isin")
    @classmethod
    def _validate_isin(cls, v: str | None) -> str | None:
        if v is None:
            return None
        iso = v.upper().strip()
        if len(iso) != 12 or not iso[:2].isalpha():
            raise ValueError(f"invalid ISIN: {v!r}")
        return iso

    @model_validator(mode="after")
    def _validate_option_fields(self) -> InstrumentIdentity:
        if self.security_type == SecurityType.OPTION:
            missing = [
                f
                for f in ("expiry", "strike", "option_type", "underlying")
                if getattr(self, f) is None
            ]
            if missing:
                raise ValueError(f"option instrument requires {missing}")
        if self.segment == Segment.FO and self.security_type == SecurityType.EQUITY:
            raise ValueError("FO segment requires a derivative security_type")
        return self

    @property
    def nautilus_symbol(self) -> str:
        """Symbol used inside NautilusTrader (no venue suffix)."""
        return self.symbol.replace("|", "-").replace(" ", "_").upper()

    @property
    def nautilus_venue(self) -> str:
        suffix = ""
        if self.segment == Segment.FO:
            suffix = "FO"
        elif self.segment == Segment.IDX:
            suffix = "IDX"
        venue = self.exchange.value + suffix
        return venue

    @property
    def nautilus_instrument_id(self) -> str:
        return f"{self.nautilus_symbol}.{self.nautilus_venue}"


class OptionInstrument(InstrumentIdentity):
    """A single listed option contract; never mixed with equity records."""

    security_type: SecurityType = SecurityType.OPTION
    segment: Segment = Segment.FO
    expiry: date
    strike: float
    option_type: OptionType
    underlying: str

    @classmethod
    def build(
        cls,
        *,
        exchange: Exchange,
        underlying: str,
        expiry: date,
        strike: float,
        option_type: OptionType,
        lot_size: int = 1,
        tick_size: float = 0.05,
        lineage: Lineage | None = None,
    ) -> OptionInstrument:
        local_id = make_option_local_id(underlying, expiry, option_type, strike)
        return cls(
            instrument_id=make_instrument_id(exchange, Segment.FO, local_id),
            exchange=exchange,
            segment=Segment.FO,
            symbol=local_id,
            lot_size=lot_size,
            tick_size=tick_size,
            expiry=expiry,
            strike=strike,
            option_type=option_type,
            underlying=underlying.upper(),
            lineage=lineage,
        )


def to_nautilus_timestamp(ts: datetime) -> int:
    """Convert a timezone-aware datetime to unix nanoseconds."""
    return int(ts.timestamp() * 1_000_000_000)


__all__ = [
    "ID_SEPARATOR",
    "InstrumentIdentity",
    "OptionInstrument",
    "make_instrument_id",
    "parse_instrument_id",
    "make_option_local_id",
    "to_nautilus_timestamp",
]
