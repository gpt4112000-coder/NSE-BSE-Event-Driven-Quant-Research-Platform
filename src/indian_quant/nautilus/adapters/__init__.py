"""Adapter implementations (backtest now; Upstox live later)."""

from indian_quant.nautilus.adapters.backtest import BacktestResult, BacktestRunner, summarize_result

__all__ = ["BacktestResult", "BacktestRunner", "summarize_result"]
