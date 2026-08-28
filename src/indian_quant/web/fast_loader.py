"""Fast data loader that reads from cached_signals table.

Replaces the slow parquet-scanning functions in data_loader.py.
Dashboard/Signals pages call these instead of scanning 3,755 files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import sqlalchemy as sa

from indian_quant.config import load_settings


def _get_engine():
    settings = load_settings()
    db_path = str(Path(settings.storage.metadata_dsn.removeprefix("sqlite:///")))
    return sa.create_engine(f"sqlite:///{db_path}")


def _table_exists(engine, table_name: str) -> bool:
    return sa.inspect(engine).has_table(table_name)


def get_cached_signals() -> pd.DataFrame:
    """Read all cached signals as DataFrame."""
    engine = _get_engine()
    if not _table_exists(engine, "cached_signals"):
        return pd.DataFrame()
    return pd.read_sql("SELECT * FROM cached_signals", engine)


def get_latest_signals_cached() -> dict[str, Any]:
    """Fast replacement for data_loader.get_latest_signals()."""
    df = get_cached_signals()
    if df.empty:
        return {"date": "", "buys": [], "avoids": [], "total_scanned": 0}

    latest_date = df["signal_date"].max()
    today = df[df["signal_date"] == latest_date]

    buys = today[today["signal_type"] == "dz_hi_up"].sort_values("deliv_z", ascending=False)
    avoids = today[today["signal_type"] == "dz_hi_dn"].sort_values("deliv_z", ascending=False)

    return {
        "date": str(latest_date),
        "buys": buys.replace({pd.NA: None}).to_dict(orient="records"),
        "avoids": avoids.replace({pd.NA: None}).to_dict(orient="records"),
        "total_scanned": int(len(today)),
    }


def get_cached_signal_for_symbol(symbol: str) -> dict[str, Any] | None:
    """Get cached signal for a single symbol."""
    engine = _get_engine()
    if not _table_exists(engine, "cached_signals"):
        return None
    df = pd.read_sql(
        "SELECT * FROM cached_signals WHERE symbol = ?",
        engine, params=(symbol.upper(),),
    )
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def get_cached_signals_summary() -> dict[str, Any]:
    """Summary stats for dashboard cards."""
    df = get_cached_signals()
    if df.empty:
        return {"total": 0, "buys": 0, "avoids": 0, "date": ""}

    latest_date = df["signal_date"].max()
    today = df[df["signal_date"] == latest_date]

    return {
        "date": str(latest_date),
        "total": int(len(today)),
        "buys": int((today["signal_type"] == "dz_hi_up").sum()),
        "avoids": int((today["signal_type"] == "dz_hi_dn").sum()),
    }
