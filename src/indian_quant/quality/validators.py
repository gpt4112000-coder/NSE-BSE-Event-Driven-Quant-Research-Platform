"""Data quality engine: validators, anomaly checks, completeness, reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from indian_quant.schemas import MarketBar


@dataclass
class QualityIssue:
    severity: str  # "error" | "warning"
    code: str
    detail: str


@dataclass
class QualityReport:
    dataset: str
    n_rows: int = 0
    n_errors: int = 0
    n_warnings: int = 0
    issues: list[QualityIssue] = field(default_factory=list)

    def add(self, issue: QualityIssue) -> None:
        self.issues.append(issue)
        if issue.severity == "error":
            self.n_errors += 1
        else:
            self.n_warnings += 1

    @property
    def passed(self) -> bool:
        return self.n_errors == 0

    def to_dict(self) -> dict:
        return {
            "dataset": self.dataset,
            "n_rows": self.n_rows,
            "n_errors": self.n_errors,
            "n_warnings": self.n_warnings,
            "issues": [
                {"severity": i.severity, "code": i.code, "detail": i.detail}
                for i in self.issues
            ],
        }


def validate_ohlc(bars: list[MarketBar], report: QualityReport) -> None:
    for bar in bars:
        if bar.high < max(bar.open, bar.close):
            report.add(QualityIssue("error", "OHLC_HIGH", f"{bar.instrument_id}@{bar.timestamp}"))
        if bar.low > min(bar.open, bar.close):
            report.add(QualityIssue("error", "OHLC_LOW", f"{bar.instrument_id}@{bar.timestamp}"))
        if bar.low > bar.high:
            report.add(QualityIssue("error", "OHLC_ORDER", f"{bar.instrument_id}@{bar.timestamp}"))


def detect_duplicates(bars: list[MarketBar], report: QualityReport) -> list[MarketBar]:
    seen: dict[tuple, MarketBar] = {}
    unique: list[MarketBar] = []
    for bar in bars:
        key = (bar.instrument_id, bar.timeframe.value, int(bar.timestamp.timestamp()))
        if key in seen:
            prev = seen[key]
            if abs(prev.close - bar.close) > 1e-9:
                report.add(
                    QualityIssue(
                        "warning",
                        "DUPLICATE_CONFLICT",
                        f"{bar.instrument_id}@{bar.timestamp} close {prev.close} vs {bar.close}",
                    )
                )
            else:
                report.add(QualityIssue("warning", "DUPLICATE", f"{bar.instrument_id}@{bar.timestamp}"))
            continue
        seen[key] = bar
        unique.append(bar)
    return unique


def detect_price_anomalies(
    bars: list[MarketBar],
    report: QualityReport,
    *,
    max_abs_return: float = 0.35,
) -> None:
    by_instrument: dict[str, list[MarketBar]] = {}
    for bar in bars:
        by_instrument.setdefault(bar.instrument_id, []).append(bar)
    for instrument_id, series in by_instrument.items():
        ordered = sorted(series, key=lambda b: b.timestamp)
        for prev, cur in zip(ordered, ordered[1:], strict=False):
            if prev.close <= 0:
                continue
            ret = cur.close / prev.close - 1.0
            if abs(ret) > max_abs_return:
                report.add(
                    QualityIssue(
                        "warning",
                        "PRICE_JUMP",
                        f"{instrument_id} {prev.timestamp.date()}->{cur.timestamp.date()} "
                        f"return {ret:.2%}",
                    )
                )


def detect_missing_sessions(
    bars: list[MarketBar],
    report: QualityReport,
    *,
    holidays: set[date] | None = None,
    max_gap_days: int = 10,
) -> None:
    """Flag weekday gaps longer than a weekend that are not known holidays."""
    holidays = holidays or set()
    by_instrument: dict[str, list[MarketBar]] = {}
    for bar in bars:
        by_instrument.setdefault(bar.instrument_id, []).append(bar)
    for instrument_id, series in by_instrument.items():
        ordered = sorted(series, key=lambda b: b.timestamp)
        for prev, cur in zip(ordered, ordered[1:], strict=False):
            gap_days = (cur.timestamp.date() - prev.timestamp.date()).days
            if gap_days <= 1 or gap_days > max_gap_days:
                continue
            missing_weekdays = _weekdays_between(prev.timestamp.date(), cur.timestamp.date())
            unexplained = [d for d in missing_weekdays if d not in holidays]
            if unexplained:
                report.add(
                    QualityIssue(
                        "warning",
                        "MISSING_SESSIONS",
                        f"{instrument_id} missing {len(unexplained)} sessions "
                        f"{unexplained[0]}..{unexplained[-1]}",
                    )
                )


def _weekdays_between(start: date, end: date) -> list[date]:
    days: list[date] = []
    cursor = start + timedelta(days=1)
    while cursor < end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def run_quality_suite(
    bars: list[MarketBar],
    *,
    dataset: str,
    holidays: set[date] | None = None,
    max_gap_days: int = 10,
) -> tuple[QualityReport, list[MarketBar]]:
    report = QualityReport(dataset=dataset, n_rows=len(bars))
    validate_ohlc(bars, report)
    unique = detect_duplicates(bars, report)
    detect_price_anomalies(unique, report)
    detect_missing_sessions(unique, report, holidays=holidays, max_gap_days=max_gap_days)
    return report, unique


def frame_quality_summary(df: pd.DataFrame) -> pd.DataFrame:
    return df.describe(include="all").transpose()
