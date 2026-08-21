"""Upstox execution client boundary (Phase 7 scaffold).

Mirrors the NautilusTrader ExecutionClient concepts so the eventual
implementation maps 1:1: connect, submit, modify, cancel, reconciliation.
Order lifecycle testing happens against the Upstox sandbox first -
never live markets. These methods intentionally raise until Phase 7;
the interface is the contract that matters now.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from indian_quant.config.settings import UpstoxConfig


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class ProductType(StrEnum):
    INTRADAY = "I"
    DELIVERY = "D"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"


@dataclass(frozen=True)
class SandboxOrderRequest:
    instrument_key: str
    quantity: int
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    product: ProductType = ProductType.INTRADAY
    limit_price: float | None = None
    trigger_price: float | None = None


@dataclass(frozen=True)
class ExecutionReport:
    order_id: str
    status: str
    filled_qty: int = 0
    avg_price: float | None = None
    raw: dict[str, Any] | None = None


class UpstoxExecutionClient:
    """Sandbox-first execution boundary aligned with Nautilus ExecutionClient."""

    def __init__(self, config: UpstoxConfig) -> None:
        if not config.sandbox:
            raise RuntimeError(
                "refusing to construct a live execution client; sandbox only in this phase"
            )
        self.config = config

    async def connect(self) -> None:
        raise NotImplementedError("Phase 7")

    async def generate_account_state(self) -> dict[str, Any]:
        raise NotImplementedError("Phase 7")

    async def submit_order(self, request: SandboxOrderRequest) -> ExecutionReport:
        raise NotImplementedError("Phase 7")

    async def modify_order(self, order_id: str, *, quantity: int | None = None,
                           limit_price: float | None = None) -> ExecutionReport:
        raise NotImplementedError("Phase 7")

    async def cancel_order(self, order_id: str) -> ExecutionReport:
        raise NotImplementedError("Phase 7")

    async def reconcile(self) -> list[ExecutionReport]:
        """Pull all open/completed orders and rebuild execution state."""
        raise NotImplementedError("Phase 7")
