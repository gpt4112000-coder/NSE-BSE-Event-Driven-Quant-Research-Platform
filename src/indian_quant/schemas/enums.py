"""Canonical enumerations shared across all data contracts."""

from __future__ import annotations

from enum import StrEnum


class Exchange(StrEnum):
    NSE = "NSE"
    BSE = "BSE"


class Segment(StrEnum):
    EQ = "EQ"
    SME = "SME"
    FO = "FO"
    MF = "MF"
    DEBT = "DEBT"
    IDX = "IDX"
    CURRENCY = "CURRENCY"
    COMMODITY = "COMMODITY"


class SecurityType(StrEnum):
    EQUITY = "EQUITY"
    INDEX = "INDEX"
    ETF = "ETF"
    SGB = "SGB"
    FUTURE = "FUTURE"
    OPTION = "OPTION"
    MUTUAL_FUND = "MUTUAL_FUND"
    BOND = "BOND"


class Timeframe(StrEnum):
    MIN_1 = "1m"
    MIN_5 = "5m"
    MIN_15 = "15m"
    MIN_30 = "30m"
    MIN_60 = "60m"
    DAY = "1d"
    WEEK = "1w"
    MONTH = "1M"

    @property
    def pandas_freq(self) -> str:
        return {
            Timeframe.MIN_1: "1min",
            Timeframe.MIN_5: "5min",
            Timeframe.MIN_15: "15min",
            Timeframe.MIN_30: "30min",
            Timeframe.MIN_60: "60min",
            Timeframe.DAY: "1D",
            Timeframe.WEEK: "W-MON",
            Timeframe.MONTH: "ME",
        }[self]

    @property
    def nautilus_aggregation(self) -> str:
        return {
            Timeframe.MIN_1: "MINUTE",
            Timeframe.MIN_5: "MINUTE",
            Timeframe.MIN_15: "MINUTE",
            Timeframe.MIN_30: "MINUTE",
            Timeframe.MIN_60: "HOUR",
            Timeframe.DAY: "DAY",
            Timeframe.WEEK: "WEEK",
            Timeframe.MONTH: "MONTH",
        }[self]


class CorporateActionType(StrEnum):
    DIVIDEND = "DIVIDEND"
    BONUS = "BONUS"
    SPLIT = "SPLIT"
    RIGHTS = "RIGHTS"
    MERGER = "MERGER"
    DEMERGER = "DEMERGER"
    BUYBACK = "BUYBACK"
    OTHER = "OTHER"


class AdjustmentStatus(StrEnum):
    UNADJUSTED = "UNADJUSTED"
    SPLIT_ADJUSTED = "SPLIT_ADJUSTED"
    DIVIDEND_ADJUSTED = "DIVIDEND_ADJUSTED"
    FULLY_ADJUSTED = "FULLY_ADJUSTED"
    UNKNOWN = "UNKNOWN"


class QualityStatus(StrEnum):
    RAW = "RAW"
    VALIDATED = "VALIDATED"
    SUSPECT = "SUSPECT"
    REJECTED = "REJECTED"


class OptionType(StrEnum):
    CE = "CE"
    PE = "PE"


class DataSource(StrEnum):
    NSE = "NSE"
    BSE = "BSE"
    UPSTOX = "UPSTOX"
    MANUAL = "MANUAL"


SCHEMA_VERSION = 1

class SignalName(StrEnum):
    DZ_HI_UP = "dz_hi_up"
    DZ_HI_DN = "dz_hi_dn"
    DZ_LO_UP = "dz_lo_up"
    SPIKE_70 = "spike_70"
    STREAK3 = "streak3"
