"""Feature engineering on validated bars."""

from __future__ import annotations

import numpy as np
import pandas as pd


def momentum(df: pd.DataFrame, window: int = 20) -> pd.Series:
    return df["close"].pct_change(window)


def realized_volatility(df: pd.DataFrame, window: int = 20, annualize: bool = True) -> pd.Series:
    ret = df["close"].pct_change()
    vol = ret.rolling(window).std()
    if annualize:
        vol = vol * np.sqrt(252)
    return vol


def volume_zscore(df: pd.DataFrame, window: int = 30) -> pd.Series:
    mean = df["volume"].rolling(window).mean()
    std = df["volume"].rolling(window).std().replace(0, np.nan)
    return (df["volume"] - mean) / std


def delivery_anomaly(delivery_pct: pd.Series, window: int = 30) -> pd.Series:
    mean = delivery_pct.rolling(window).mean()
    std = delivery_pct.rolling(window).std().replace(0, np.nan)
    return (delivery_pct - mean) / std


def market_regime(
    df: pd.DataFrame,
    *,
    trend_window: int = 50,
    vol_window: int = 20,
    vol_quantile: float = 0.7,
) -> pd.Series:
    """Simple regime labels: BULL / BEAR / SIDEWAYS crossed with volatility."""
    close = df["close"]
    trend = close - close.rolling(trend_window).mean()
    vol = close.pct_change().rolling(vol_window).std()
    high_vol = vol > vol.quantile(vol_quantile)

    def label(i: int) -> str:
        if np.isnan(trend.iloc[i]):
            return "SIDEWAYS"
        if high_vol.iloc[i]:
            return "HIGH_VOL"
        if trend.iloc[i] > 0:
            return "BULL"
        if trend.iloc[i] < 0:
            return "BEAR"
        return "SIDEWAYS"

    return pd.Series([label(i) for i in range(len(df))], index=df.index, name="regime")


def build_feature_frame(
    df: pd.DataFrame,
    *,
    delivery_pct: pd.Series | None = None,
) -> pd.DataFrame:
    out = df.copy().sort_values("timestamp").reset_index(drop=True)
    out["return_1d"] = out["close"].pct_change()
    out["momentum_20d"] = momentum(out, 20)
    out["volatility_20d"] = realized_volatility(out, 20)
    out["volume_zscore_30d"] = volume_zscore(out, 30)
    if delivery_pct is not None:
        out["delivery_anomaly_30d"] = delivery_anomaly(delivery_pct.reset_index(drop=True))
    out["regime"] = market_regime(out)
    return out
