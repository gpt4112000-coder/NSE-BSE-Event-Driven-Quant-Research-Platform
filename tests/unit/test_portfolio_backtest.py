"""Portfolio backtest tests: sizing, stops, slots, clusters, costs."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from indian_quant.research.portfolio_backtest import (  # noqa: E402
    StrategyConfig,
    run_portfolio,
)


def make_frame(symbol: str, closes, delivs: list[float], segment="EQ"):
    dates = pd.date_range("2026-01-01", periods=len(closes), freq="B", tz="UTC")
    df = pd.DataFrame({
        "date": dates,
        "symbol": symbol,
        "segment": segment,
        "close": closes,
        "deliv_pct": delivs,
        "volume": np.full(len(closes), 500_000.0),
    })
    from indian_quant.features.delivery import add_features, prepare_frame

    return add_features(prepare_frame(df))


def flat_then_spike(base=100.0, n=40, spike_day=20):
    closes = [base] * n
    deliv = [45.0] * n
    return closes, deliv, spike_day


class TestPortfolioBacktest:
    def _cfg(self, **kw):
        defaults = dict(signal="dz_hi_up", price_min=1.0, price_max=1e9,
                        min_turnover=0.0, hold_days=10, stop_pct=0.07,
                        max_positions=8, capital=25_000.0, risk_pct=1.0,
                        cost_bps=107.0, cluster_entries=False)
        defaults.update(kw)
        return StrategyConfig(**defaults)

    def test_single_trade_lifecycle(self):
        # engineered: z>=2 + up-move fires at day 19; hold to horizon (10d)
        closes = [100.0] * 19 + [101.0] * 21
        delivs = [45.0] * 18 + [90.0] * 22
        frames = [make_frame("TEST", closes, delivs)]
        result = run_portfolio(frames, self._cfg(hold_days=5))
        assert result.summary["n_trades"] == 1
        trade = result.trades[0]
        assert trade.symbol == "TEST"
        assert trade.reason in ("HORIZON", "DATA_END")
        # gross over 5 days of flat prices ~0 -> net ~= -107bps
        assert trade.net_bps == pytest.approx(-107.0, abs=15)

    def test_stop_exit_triggers(self):
        closes = [100.0] * 19 + [101.0] * 3 + [85.0] * 20
        delivs = [45.0] * 18 + [92.0] * 24
        frames = [make_frame("TEST", closes, delivs)]
        result = run_portfolio(frames, self._cfg())
        stops = [t for t in result.trades if t.reason == "STOP"]
        assert len(stops) == 1
        assert stops[0].net_bps < -700  # 7% stop minus costs

    def test_max_positions_constraint(self):
        # three symbols fire the same day; only 2 slots allowed
        frames = []
        for sym in ("AAA", "BBB", "CCC"):
            closes = [100.0] * 19 + [110.0] * 21
            delivs = [45.0] * 18 + [95.0] * 22
            f = make_frame(sym, closes, delivs)
            f["deliv_z"] = f["deliv_z"] + {"AAA": 3, "BBB": 2, "CCC": 1}[
                sym]  # deterministic priority
            frames.append(f)
        result = run_portfolio(frames, self._cfg(max_positions=2))
        entered = {t.symbol for t in result.trades}
        assert entered == {"AAA", "BBB"}

    def test_cluster_first_fire_only(self):
        # delivery >=60 with rising price fires spike_70 on consecutive days;
        # cluster_entries must produce exactly ONE entry
        closes = list(np.linspace(100, 130, 45))
        delivs = [80.0] * 45
        frames = [make_frame("TEST", closes, delivs)]
        cfg = StrategyConfig(signal="spike_70", price_min=1.0, price_max=1e9,
                             min_turnover=0.0, hold_days=3,
                             cluster_entries=True)
        result = run_portfolio(frames, cfg)
        assert result.summary["n_trades"] == 1

    def test_costs_applied_per_round_trip(self):
        closes = [100.0] * 19 + [101.0] * 21
        delivs = [45.0] * 18 + [90.0] * 22
        frames = [make_frame("TEST", closes, delivs)]
        r_free = run_portfolio(frames, self._cfg(cost_bps=0.0, hold_days=5))
        r_cost = run_portfolio(frames, self._cfg(cost_bps=107.0, hold_days=5))
        g_free = r_free.trades[0].net_bps
        g_cost = r_cost.trades[0].net_bps
        assert g_free == pytest.approx(g_cost + 107.0, abs=2)
