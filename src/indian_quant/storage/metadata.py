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
            CREATE INDEX IF NOT EXISTS idx_symbol_events_isin ON symbol_events(isin, effective_date);
            CREATE INDEX IF NOT EXISTS idx_jobs_tool ON jobs(tool, started_at);
            CREATE INDEX IF NOT EXISTS idx_runs_kind ON runs(kind, started_at);
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
