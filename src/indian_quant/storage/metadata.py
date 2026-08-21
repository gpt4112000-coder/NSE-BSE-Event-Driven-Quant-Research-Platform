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

    def close(self) -> None:
        self._con.close()
