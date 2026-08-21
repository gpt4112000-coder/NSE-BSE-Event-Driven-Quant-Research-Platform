"""India delivery-market fee schedule as a NautilusTrader FeeModel.

Side-aware per-fill commission:
    BUY : brokerage_bps + stamp_buy_bps   (+ flat fee / order)
    SELL: brokerage_bps + stt_sell_bps    (+ flat fee / order)

Defaults reflect typical Indian discount-broker delivery costs. Because the
model plugs into add_venue(fee_model=...), commissions flow automatically
into fills, positions and account reports.
"""

from __future__ import annotations

from nautilus_trader.backtest.models import FeeModel
from nautilus_trader.model.currencies import INR
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.objects import Money


class IndiaDeliveryFeeModel(FeeModel):
    def __init__(
        self,
        *,
        brokerage_bps: float = 3.0,
        stt_sell_bps: float = 100.0,
        stamp_buy_bps: float = 1.5,
        flat_fee_per_order: float = 0.0,
    ) -> None:
        super().__init__()
        self.brokerage_bps = brokerage_bps
        self.stt_sell_bps = stt_sell_bps
        self.stamp_buy_bps = stamp_buy_bps
        self.flat_fee_per_order = flat_fee_per_order

    def get_commission(self, order, fill_qty, fill_px, instrument):  # type: ignore[override]
        qty = float(fill_qty)
        price = float(fill_px)
        notional = qty * price
        if order.side == OrderSide.SELL:
            bps = self.brokerage_bps + self.stt_sell_bps
        else:
            bps = self.brokerage_bps + self.stamp_buy_bps
        total = notional * (bps / 10_000.0) + self.flat_fee_per_order
        return Money(round(total, 2), INR)


__all__ = ["IndiaDeliveryFeeModel"]
