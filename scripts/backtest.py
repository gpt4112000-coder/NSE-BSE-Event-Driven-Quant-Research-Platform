"""Run an SMA-cross backtest from the Nautilus catalog.

Usage:
    python scripts/backtest.py --symbol RELIANCE --fast 10 --slow 30
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indian_quant.config import load_settings
from indian_quant.nautilus.adapters.backtest import BacktestRunner, summarize_result
from indian_quant.research import ExperimentTracker
from indian_quant.storage import MetadataStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SMA cross backtest")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--fast", type=int, default=10)
    parser.add_argument("--slow", type=int, default=30)
    parser.add_argument("--trade-size", type=int, default=100)
    parser.add_argument("--config", default=None)
    args = parser.parse_args()

    settings = load_settings(args.config)
    runner = BacktestRunner(settings)
    result = runner.run_sma_cross(
        symbol=args.symbol.upper(),
        fast=args.fast,
        slow=args.slow,
        trade_size=args.trade_size,
    )
    metrics = summarize_result(result)

    run_dir = settings.data_root / "normalized" / "backtests" / result.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    fills_out = result.fills.reset_index(drop=True) if not result.fills.empty else result.fills
    fills_out.to_parquet(run_dir / "fills.parquet", index=False)
    if not result.positions.empty:
        result.positions.reset_index(drop=True).to_parquet(run_dir / "positions.parquet", index=False)

    metadata = MetadataStore(settings.storage.metadata_dsn)
    tracker = ExperimentTracker(metadata)
    tracker.record(kind="backtest_sma", config=result.config, metrics=metrics)

    print(json.dumps(metrics, indent=2, default=str))

    import subprocess

    subprocess.run(
        [sys.executable, str(Path(__file__).parent / "friction_report.py"),
         "--run-id", result.run_id],
        check=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
