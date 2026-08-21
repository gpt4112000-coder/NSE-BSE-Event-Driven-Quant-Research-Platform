"""Sample event-driven strategy: SMA cross on daily bars.

Runs unchanged against historical replay, backtest, and (later) live
Upstox market data - the core Phase 6 exit condition.
"""

from __future__ import annotations

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.trading.strategy import Strategy


class SmaCrossConfig(StrategyConfig):  # type: ignore[misc]
    instrument_id: str
    bar_type: str
    fast: int = 10
    slow: int = 30
    trade_size: int = 100


class SmaCross(Strategy):
    def __init__(self, config: SmaCrossConfig) -> None:
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.bar_type = BarType.from_str(config.bar_type)
        self.fast = config.fast
        self.slow = config.slow
        self.trade_size = config.trade_size
        self.closes: list[float] = []

    def on_start(self) -> None:
        self.subscribe_bars(self.bar_type)

    def on_bar(self, bar: Bar) -> None:
        self.closes.append(float(bar.close))
        if len(self.closes) < self.slow:
            return
        fast_mean = sum(self.closes[-self.fast :]) / self.fast
        slow_mean = sum(self.closes[-self.slow :]) / self.slow
        target = 1 if fast_mean > slow_mean else (-1 if fast_mean < slow_mean else 0)
        self._rebalance_to(target)

    def _rebalance_to(self, target_side: int) -> None:
        inst = self.cache.instrument(self.instrument_id)
        if inst is None:
            return
        flat = self.portfolio.is_flat(self.instrument_id)
        pos = 0 if flat else int(self.portfolio.net_position(self.instrument_id))
        if pos == target_side:
            return
        if pos != 0:
            close_order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.SELL if pos > 0 else OrderSide.BUY,
                quantity=inst.make_qty(abs(pos)),
            )
            self.submit_order(close_order)
        if target_side != 0:
            entry = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY if target_side > 0 else OrderSide.SELL,
                quantity=inst.make_qty(self.trade_size),
            )
            self.submit_order(entry)

    def on_stop(self) -> None:
        self.unsubscribe_bars(self.bar_type)
