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

    metadata = MetadataStore(settings.storage.metadata_dsn)
    tracker = ExperimentTracker(metadata)
    tracker.record(kind="backtest_sma", config=result.config, metrics=metrics)

    print(json.dumps(metrics, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
