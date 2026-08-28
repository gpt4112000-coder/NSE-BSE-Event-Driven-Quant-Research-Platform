"""Read-only data loading for web dashboard. No mutations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _sanitize(obj):
    """Convert numpy/pandas types to plain Python for safe Jinja2 rendering."""
    return json.loads(json.dumps(obj, default=str))


def _settings():
    from indian_quant.config import load_settings
    return load_settings()


def get_paper_summary() -> dict[str, Any]:
    settings = _settings()
    db = Path(settings.storage.metadata_dsn.removeprefix("sqlite:///"))
    if not db.exists():
        return {"open": 0, "settled": 0, "avg_net_bps": None, "hit_rate": None}
    con = sqlite3.connect(str(db))
    settled = con.execute(
        """SELECT COUNT(*), AVG(realized_net_bps),
           SUM(realized_net_bps>0)*1.0/COUNT(*) FROM paper_signals WHERE status='SETTLED'"""
    ).fetchone()
    open_n = con.execute(
        "SELECT COUNT(*) FROM paper_signals WHERE status='OPEN'"
    ).fetchone()[0]
    cursor = con.execute("SELECT * FROM paper_signals WHERE status='OPEN' ORDER BY created_at DESC")
    cols = [d[0] for d in cursor.description]
    open_rows = []
    for row in cursor.fetchall():
        entry = {}
        for col, val in zip(cols, row, strict=False):
            if isinstance(val, bytes):
                val = val.decode()
            elif not isinstance(val, (int, float, str, bool, type(None))):
                val = str(val)
            entry[col] = val
        open_rows.append(entry)
    con.close()
    result = {
        "open": int(open_n),
        "settled": int(settled[0]) if settled[0] else 0,
        "avg_net_bps": float(round(settled[1], 1)) if settled[1] is not None else None,
        "hit_rate": float(round(settled[2], 3)) if settled[2] is not None else None,
        "open_positions": open_rows,
    }
    return _sanitize(result)


def get_gate_progress() -> dict[str, Any]:
    s = get_paper_summary()
    target = 20
    floor_bps = 25.0
    pct = min(100, int(s["settled"] / target * 100)) if s["settled"] else 0
    net_ok = (s["avg_net_bps"] is not None and s["avg_net_bps"] >= floor_bps)
    passed = s["settled"] >= target and net_ok
    result = {
        "target": int(target),
        "settled": int(s["settled"]),
        "pct": int(pct),
        "avg_net_bps": s["avg_net_bps"],
        "floor_bps": float(floor_bps),
        "net_ok": bool(net_ok),
        "passed": bool(passed),
    }
    return _sanitize(result)


def get_latest_signals() -> dict[str, Any]:
    dl_dir = _settings().normalized_dir / "delivery" / "NSE"
    rows: list[dict[str, Any]] = []
    latest_date = ""
    for path in sorted(dl_dir.glob("*.parquet")):
        try:
            raw = pd.read_parquet(path, columns=["date", "symbol", "segment", "close", "deliv_pct", "volume"])
        except Exception:
            continue
        if raw.empty or len(raw) < 20:
            continue
        frame = raw.copy()
        frame["date_str"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
        d = frame["date_str"].iloc[-1]
        if d > latest_date:
            latest_date = d
        last = frame.iloc[-1]
        prev = frame.iloc[-2] if len(frame) > 1 else frame.iloc[-1]
        deliv_series = pd.to_numeric(frame["deliv_pct"], errors="coerce").dropna()
        if len(deliv_series) < 15:
            continue
        mean = deliv_series.tail(30).mean()
        std = deliv_series.tail(30).std()
        z = (last["deliv_pct"] - mean) / std if std > 0 else np.nan
        ret = (float(last["close"]) / float(prev["close"]) - 1.0) if float(prev["close"]) > 0 else 0.0
        rows.append({
            "symbol": str(last["symbol"]),
            "segment": str(last["segment"]) if "segment" in frame.columns else "EQ",
            "close": round(float(last["close"]), 2),
            "deliv_pct": round(float(last["deliv_pct"]), 1) if not pd.isna(last["deliv_pct"]) else None,
            "deliv_z": round(float(z), 2) if not pd.isna(z) else None,
            "ret_1d_pct": round(ret * 100, 2),
            "_date": d,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return {"date": "", "buys": [], "avoids": [], "total_scanned": 0}
    today = df[df["_date"] == latest_date].copy()
    buys = today[(today["deliv_z"] >= 2) & (today["ret_1d_pct"] >= 0.5)]
    avoids = today[(today["deliv_z"] >= 2) & (today["ret_1d_pct"] <= -0.5)]
    buys = buys.sort_values("deliv_z", ascending=False)
    avoids = avoids.sort_values("deliv_z", ascending=False)

    result = {
        "date": str(latest_date),
        "buys": buys.replace(np.nan, None).to_dict(orient="records"),
        "avoids": avoids.replace(np.nan, None).to_dict(orient="records"),
        "total_scanned": int(len(today)),
    }
    return _sanitize(result)


def get_research_results() -> dict[str, Any]:
    gen_dir = Path("docs/research/generated")
    out: dict[str, Any] = {}
    for name in ("delivery_sweep.json", "delivery_r2b.json", "event_type_car.json",
                  "deflation_verdict.json", "sme_dz_hi_up_5d.json", "entry_analysis.json"):
        path = gen_dir / name
        if path.exists():
            key = name.replace(".json", "")
            out[key] = _sanitize(json.loads(path.read_text()))
    return out


def get_announcements(symbol: str) -> list[dict[str, Any]]:
    path = _settings().normalized_dir / "announcements" / "NSE" / f"{symbol}.parquet"
    if not path.exists():
        return []
    df = pd.read_parquet(path)
    return _sanitize(df.tail(20).replace(np.nan, None).to_dict(orient="records"))


def get_available_announcement_symbols() -> list[str]:
    dl_dir = _settings().normalized_dir / "announcements" / "NSE"
    if not dl_dir.exists():
        return []
    return sorted(p.stem for p in dl_dir.glob("*.parquet"))
