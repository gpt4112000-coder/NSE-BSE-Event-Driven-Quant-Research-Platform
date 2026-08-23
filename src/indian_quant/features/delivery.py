"""Delivery-percentage signal features.

Research premise: in NSE cash + SME segments, the share of traded quantity
actually delivered (DELIV_PER) separates genuine accumulation/distribution
from intraday square-offs. High delivery on an up-move suggests real demand;
high delivery on a down-move suggests distribution; low delivery on an
up-move suggests short covering that rarely sustains.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ("date", "symbol", "close", "deliv_pct")


def prepare_frame(df: pd.DataFrame, *, min_rows: int = 40) -> pd.DataFrame | None:
    """Clean + sort a symbol's delivery frame; None when unusable."""
    if df.empty:
        return None
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], utc=True)
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out["deliv_pct"] = pd.to_numeric(out["deliv_pct"], errors="coerce")
    out = out.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
    if len(out) < min_rows:
        return None
    return out


def add_features(df: pd.DataFrame, *, window: int = 30) -> pd.DataFrame:
    """Append ret_1d, deliv_z, hi_deliv flags, streak counters."""
    out = df.copy()
    out["ret_1d"] = out["close"].pct_change()

    mean = out["deliv_pct"].rolling(window, min_periods=15).mean()
    std = out["deliv_pct"].rolling(window, min_periods=15).std()
    std = std.replace(0, np.nan)
    out["deliv_z"] = (out["deliv_pct"] - mean) / std

    out["hi_deliv"] = out["deliv_pct"] >= 60

    flag = (out["deliv_pct"] >= 60).astype(int)
    group = flag * (flag.groupby((flag != flag.shift()).cumsum()).cumcount() + 1)
    out["hi_streak"] = group.where(flag > 0, 0)
    return out


def signal_mask(frame: pd.DataFrame, name: str) -> pd.Series:
    """Boolean firing mask for each named delivery signal."""
    z = frame["deliv_z"]
    ret = frame["ret_1d"]

    if name == "dz_hi_up":
        return (z >= 2) & (ret >= 0.005)
    if name == "dz_hi_dn":
        return (z >= 2) & (ret <= -0.005)
    if name == "dz_lo_up":
        return (z <= -2) & (ret >= 0.005)
    if name == "spike_70":
        return frame["deliv_pct"] >= 70
    if name == "streak3":
        return frame["hi_streak"] >= 3
    raise KeyError(f"unknown signal: {name}")


SIGNAL_NAMES = ("dz_hi_up", "dz_hi_dn", "dz_lo_up", "spike_70", "streak3")


__all__ = [
    "SIGNAL_NAMES",
    "add_features",
    "prepare_frame",
    "signal_mask",
]
