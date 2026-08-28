"""Operational metadata store (SQLite by default, Postgres-ready DSN design).

Only operational metadata lives here: instruments, ingestion jobs, research
runs, registered sources and quality reports. Never OHLCV rows.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat()


class MetadataStore:
    def __init__(self, dsn: str) -> None:
        if not dsn.startswith("sqlite:///"):
            raise NotImplementedError(
                "only sqlite DSNs are wired; postgres uses the same schema via a driver swap"
            )
        path = dsn.removeprefix("sqlite:///")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(path)
        self._con.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        self._con.executescript(
            """
            CREATE TABLE IF NOT EXISTS instruments (
                instrument_id TEXT PRIMARY KEY,
                exchange TEXT NOT NULL,
                segment TEXT NOT NULL,
                symbol TEXT NOT NULL,
                isin TEXT,
                security_type TEXT,
                lot_size INTEGER,
                tick_size REAL,
                nautilus_id TEXT,
                registered_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                tool TEXT NOT NULL,
                source TEXT NOT NULL,
                params_json TEXT,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                raw_hash TEXT,
                rows INTEGER,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                dataset_hash TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                metrics_json TEXT
            );
            CREATE TABLE IF NOT EXISTS quality_reports (
                report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                n_rows INTEGER,
                n_errors INTEGER,
                n_warnings INTEGER,
                report_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS symbol_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                isin TEXT NOT NULL,
                exchange TEXT NOT NULL,
                event_type TEXT NOT NULL,
                from_symbol TEXT,
                to_symbol TEXT,
                effective_date TEXT NOT NULL,
                note TEXT,
                source TEXT,
                recorded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS paper_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                segment TEXT,
                side TEXT NOT NULL DEFAULT 'BUY',
                close_at_signal REAL NOT NULL,
                qty INTEGER NOT NULL,
                horizon_days INTEGER NOT NULL,
                stop_pct REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                exit_date TEXT,
                exit_close REAL,
                realized_net_bps REAL,
                note TEXT
            );
            CREATE TABLE IF NOT EXISTS daily_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                suggestion_date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                segment TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                direction TEXT NOT NULL DEFAULT 'BUY',
                close_at_signal REAL NOT NULL,
                deliv_pct REAL,
                deliv_z REAL,
                vol_z REAL,
                entry_zone_low REAL,
                entry_zone_high REAL,
                stop_loss REAL,
                target_price REAL,
                horizon_days INTEGER NOT NULL,
                qty_suggested INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                actual_exit_date TEXT,
                actual_exit_close REAL,
                actual_return_bps REAL,
                predicted_return_bps REAL,
                hit BOOLEAN,
                note TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sugg_date ON daily_suggestions(suggestion_date);
            CREATE INDEX IF NOT EXISTS idx_sugg_symbol ON daily_suggestions(symbol);
            CREATE INDEX IF NOT EXISTS idx_sugg_status ON daily_suggestions(status);
            CREATE INDEX IF NOT EXISTS idx_paper_status ON paper_signals(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_symbol_events_isin ON symbol_events(isin, effective_date);
            CREATE INDEX IF NOT EXISTS idx_jobs_tool ON jobs(tool, started_at);
            CREATE INDEX IF NOT EXISTS idx_runs_kind ON runs(kind, started_at);

            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                last_login TEXT,
                is_active BOOLEAN NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

            CREATE TABLE IF NOT EXISTS watchlists (
                watchlist_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL DEFAULT 'NSE',
                added_at TEXT NOT NULL,
                notes TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                UNIQUE(user_id, symbol)
            );
            CREATE INDEX IF NOT EXISTS idx_watchlists_user ON watchlists(user_id);

            CREATE TABLE IF NOT EXISTS watchlist_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                watchlist_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                signal_date TEXT,
                signal_type TEXT,
                close REAL,
                deliv_pct REAL,
                deliv_z REAL,
                vol_z REAL,
                ret_1d REAL,
                rsi REAL,
                macd REAL,
                macd_signal REAL,
                sma_20 REAL,
                sma_50 REAL,
                atr_14 REAL,
                entry_zone_low REAL,
                entry_zone_high REAL,
                stop_loss REAL,
                target_price REAL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (watchlist_id) REFERENCES watchlists(watchlist_id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_ws_signals_user ON watchlist_signals(user_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_ws_signals_unique ON watchlist_signals(watchlist_id);
            """
        )
        self._con.commit()

    def register_instrument(self, identity: dict[str, Any]) -> None:
        self._con.execute(
            """
            INSERT OR REPLACE INTO instruments
            (instrument_id, exchange, segment, symbol, isin, security_type,
             lot_size, tick_size, nautilus_id, registered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity["instrument_id"],
                identity["exchange"],
                identity["segment"],
                identity["symbol"],
                identity.get("isin"),
                identity.get("security_type"),
                identity.get("lot_size"),
                identity.get("tick_size"),
                identity.get("nautilus_instrument_id"),
                _now(),
            ),
        )
        self._con.commit()

    def get_instrument(self, instrument_id: str) -> dict[str, Any] | None:
        row = self._con.execute(
            "SELECT * FROM instruments WHERE instrument_id = ?", (instrument_id,)
        ).fetchone()
        return dict(row) if row else None

    def start_job(self, job_id: str, *, tool: str, source: str, params: dict | None) -> None:
        self._con.execute(
            "INSERT OR REPLACE INTO jobs (job_id, tool, source, params_json, status, started_at)"
            " VALUES (?, ?, ?, ?, 'RUNNING', ?)",
            (job_id, tool, source, json.dumps(params or {}), _now()),
        )
        self._con.commit()

    def finish_job(
        self,
        job_id: str,
        *,
        status: str,
        raw_hash: str | None = None,
        rows: int | None = None,
        error: str | None = None,
    ) -> None:
        self._con.execute(
            "UPDATE jobs SET status=?, finished_at=?, raw_hash=?, rows=?, error=? WHERE job_id=?",
            (status, _now(), raw_hash, rows, error, job_id),
        )
        self._con.commit()

    def record_run(
        self,
        run_id: str,
        *,
        kind: str,
        config_hash: str,
        dataset_hash: str | None = None,
        metrics: dict | None = None,
    ) -> None:
        self._con.execute(
            """INSERT OR REPLACE INTO runs
               (run_id, kind, config_hash, dataset_hash, started_at, finished_at, metrics_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, kind, config_hash, dataset_hash, _now(), _now(),
             json.dumps(metrics or {})),
        )
        self._con.commit()

    def record_quality_report(self, *, dataset: str, report: dict) -> int:
        cur = self._con.execute(
            "INSERT INTO quality_reports (dataset, checked_at, n_rows, n_errors, n_warnings,"
            " report_json) VALUES (?, ?, ?, ?, ?, ?)",
            (
                dataset,
                _now(),
                report.get("n_rows"),
                report.get("n_errors"),
                report.get("n_warnings"),
                json.dumps(report),
            ),
        )
        self._con.commit()
        return int(cur.lastrowid or 0)

    def record_paper_signal(self, *, symbol: str, close_at_signal: float, qty: int,
                            horizon_days: int, stop_pct: float, segment: str | None = None,
                            side: str = "BUY", note: str | None = None) -> int:
        cur = self._con.execute(
            """INSERT INTO paper_signals
               (created_at, symbol, segment, side, close_at_signal, qty,
                horizon_days, stop_pct, status, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)""",
            (_now(), symbol.upper(), segment, side, close_at_signal, qty,
             horizon_days, stop_pct, note),
        )
        self._con.commit()
        return int(cur.lastrowid or 0)

    def open_papers(self) -> list[dict]:
        rows = self._con.execute(
            "SELECT * FROM paper_signals WHERE status='OPEN' ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    def settle_paper_signal(self, paper_id: int, *, exit_date: str,
                            exit_close: float, cost_bps: float = 107.0) -> dict:
        row = self._con.execute(
            "SELECT * FROM paper_signals WHERE id=?", (paper_id,)).fetchone()
        if not row:
            raise ValueError(f"paper signal {paper_id} not found")
        p = dict(row)
        sign = 1.0 if p["side"] == "BUY" else -1.0
        gross_bps = (exit_close / p["close_at_signal"] - 1.0) * 10_000 * sign
        net_bps = gross_bps - cost_bps
        self._con.execute(
            """UPDATE paper_signals SET status='SETTLED', exit_date=?,
               exit_close=?, realized_net_bps=? WHERE id=?""",
            (exit_date, exit_close, round(net_bps, 2), paper_id),
        )
        self._con.commit()
        return {"id": paper_id, "symbol": p["symbol"],
                "gross_bps": round(gross_bps, 2),
                "realized_net_bps": round(net_bps, 2)}

    def papers_summary(self) -> dict:
        settled = self._con.execute(
            """SELECT COUNT(*) n, AVG(realized_net_bps) avg_net,
               SUM(realized_net_bps > 0)*1.0/COUNT(*) hit
               FROM paper_signals WHERE status='SETTLED'""").fetchone()
        open_n = self._con.execute(
            "SELECT COUNT(*) FROM paper_signals WHERE status='OPEN'").fetchone()[0]
        return {"settled": settled["n"], "avg_net_bps": round(settled["avg_net"], 1)
                if settled["avg_net"] is not None else None,
                "hit_rate": round(settled["hit"], 3) if settled["hit"] is not None else None,
                "open": open_n}

    def record_daily_suggestion(self, *, suggestion_date: str, symbol: str,
                                segment: str, signal_type: str,
                                close_at_signal: float, deliv_pct: float | None,
                                deliv_z: float | None, vol_z: float | None,
                                entry_zone_low: float, entry_zone_high: float,
                                stop_loss: float, target_price: float,
                                horizon_days: int, qty: int,
                                predicted_return_bps: float | None = None,
                                note: str | None = None) -> int:
        cur = self._con.execute(
            """INSERT INTO daily_suggestions
               (suggestion_date, symbol, segment, signal_type, direction,
                close_at_signal, deliv_pct, deliv_z, vol_z,
                entry_zone_low, entry_zone_high, stop_loss, target_price,
                horizon_days, qty_suggested, status,
                predicted_return_bps, note)
               VALUES (?, ?, ?, ?, 'BUY', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)""",
            (suggestion_date, symbol.upper(), segment, signal_type,
             close_at_signal, deliv_pct, deliv_z, vol_z,
             entry_zone_low, entry_zone_high, stop_loss, target_price,
             horizon_days, qty, predicted_return_bps, note),
        )
        self._con.commit()
        return int(cur.lastrowid or 0)

    def pending_suggestions(self) -> list[dict]:
        rows = self._con.execute(
            "SELECT * FROM daily_suggestions WHERE status='PENDING' ORDER BY suggestion_date DESC"
        ).fetchall()
        cols = [d[0] for d in self._con.execute("SELECT * FROM daily_suggestions LIMIT 0").description]
        return [dict(zip(cols, r, strict=False)) for r in rows]

    def settle_daily_suggestion(self, suggestion_id: int, *, exit_date: str,
                                 exit_close: float) -> dict:
        row = self._con.execute(
            "SELECT * FROM daily_suggestions WHERE id=?", (suggestion_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"suggestion {suggestion_id} not found")
        col_names = [d[0] for d in self._con.execute("SELECT * FROM daily_suggestions LIMIT 0").description]
        s = dict(zip(col_names, row, strict=False))
        gross_bps = (exit_close / s["close_at_signal"] - 1.0) * 10_000
        net_bps = gross_bps - 107.0  # measured round-trip cost
        predicted = s.get("predicted_return_bps")
        hit = (net_bps > 0) if predicted is None else ((net_bps > 0) == (predicted > 0))
        self._con.execute(
            """UPDATE daily_suggestions SET status='REALIZED',
               actual_exit_date=?, actual_exit_close=?,
               actual_return_bps=?, hit=? WHERE id=?""",
            (exit_date, exit_close, round(net_bps, 1), int(hit), suggestion_id),
        )
        self._con.commit()
        return {
            "id": suggestion_id, "symbol": s["symbol"],
            "actual_net_bps": round(net_bps, 1), "hit": bool(hit),
        }

    def suggestions_summary(self) -> dict:
        total = self._con.execute("SELECT COUNT(*) FROM daily_suggestions").fetchone()[0]
        pending = self._con.execute(
            "SELECT COUNT(*) FROM daily_suggestions WHERE status='PENDING'").fetchone()[0]
        realized = self._con.execute(
            """SELECT COUNT(*), AVG(actual_return_bps),
               SUM(hit)*1.0/COUNT(*), SUM(CASE WHEN actual_return_bps > 0 THEN 1 ELSE 0 END)*1.0/COUNT(*)
               FROM daily_suggestions WHERE status='REALIZED'""").fetchone()
        return {
            "total": total, "pending": pending,
            "realized": realized[0] or 0,
            "avg_realized_net_bps": round(realized[1], 1) if realized[1] is not None else None,
            "directional_accuracy": round(realized[2], 3) if realized[2] is not None else None,
            "profitable_pct": round(realized[3], 3) if realized[3] is not None else None,
        }

    def suggestions_by_date(self, d: str) -> list[dict]:
        rows = self._con.execute(
            "SELECT * FROM daily_suggestions WHERE suggestion_date=?", (d,)
        ).fetchall()
        cols = [desc[0] for desc in self._con.execute("SELECT * FROM daily_suggestions LIMIT 0").description]
        return [dict(zip(cols, r, strict=False)) for r in rows]

    def record_symbol_event(
        self,
        *,
        isin: str,
        exchange: str,
        event_type: str,
        effective_date: str,
        from_symbol: str | None = None,
        to_symbol: str | None = None,
        note: str | None = None,
        source: str = "MANUAL",
    ) -> int:
        if event_type not in ("RENAME", "SUSPENSION", "DELISTING", "SEGMENT_MIGRATION"):
            raise ValueError(f"unknown symbol event type: {event_type}")
        cur = self._con.execute(
            """INSERT INTO symbol_events
               (isin, exchange, event_type, from_symbol, to_symbol, effective_date,
                note, source, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (isin.upper(), exchange.upper(), event_type, from_symbol, to_symbol,
             effective_date, note, source, _now()),
        )
        self._con.commit()
        return int(cur.lastrowid or 0)

    def symbol_events_for_isin(self, isin: str) -> list[dict]:
        rows = self._con.execute(
            """SELECT * FROM symbol_events WHERE isin = ? ORDER BY effective_date""",
            (isin.upper(),),
        ).fetchall()
        return [dict(r) for r in rows]

    def current_symbol_for_isin(self, isin: str, exchange: str, as_of: str) -> str | None:
        """Symbol valid for an ISIN as of a date, applying recorded events.

        ISIN-keyed stitching is the canonical way to build continuous history
        across renames and migrations.
        """
        events = [
            e for e in self.symbol_events_for_isin(isin)
            if e["exchange"] == exchange.upper() and e["effective_date"] <= as_of
        ]
        symbol: str | None = None
        for event in events:
            if event["event_type"] == "DELISTING":
                return None
            if event["to_symbol"]:
                symbol = event["to_symbol"]
            elif event["from_symbol"] and symbol is None:
                symbol = event["from_symbol"]
        return symbol

    def close(self) -> None:
        self._con.close()
