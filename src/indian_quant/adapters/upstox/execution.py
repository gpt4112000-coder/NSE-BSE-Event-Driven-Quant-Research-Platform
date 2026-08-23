"""Upstox execution client - sandbox-first order lifecycle.

Endpoints (V3): place  POST /v3/order/place
                modify PUT  /v3/order/modify
                cancel POST /v3/order/cancel/{order_id}
Reconciliation reads (v2, read-only): order book, positions, funds.

Environment rules:
    * A sandbox token (from the Upstox developer console's sandbox section)
      is required - set UPSTOX_SANDBOX_TOKEN or upstox_sandbox_tokens.json.
    * Live routing stays physically disabled until Phase 8 sign-off
      (INDIAQUAT_ALLOW_LIVE=1 does NOT bypass this build's guardrail).
"""

from __future__ import annotations

import contextlib
import json
import os
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import httpx

from indian_quant.config.settings import UpstoxConfig

BASE_URL = "https://api.upstox.com"


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


class Validity(StrEnum):
    DAY = "DAY"
    IOC = "IOC"


@dataclass(frozen=True)
class SandboxOrderRequest:
    instrument_key: str
    quantity: int
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    product: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    limit_price: float | None = None
    trigger_price: float | None = None
    tag: str | None = None
    client_order_id: str | None = None


@dataclass(frozen=True)
class ExecutionReport:
    order_id: str
    status: str
    filled_qty: int = 0
    avg_price: float | None = None
    raw: dict[str, Any] | None = None


def _find_sandbox_token() -> str | None:
    token = os.environ.get("UPSTOX_SANDBOX_TOKEN")
    if token:
        return token
    for candidate in [Path.cwd(), *Path.cwd().parents]:
        marker = candidate / "upstox_sandbox_tokens.json"
        if marker.exists():
            try:
                value = str(json.loads(marker.read_text()).get("access_token") or "")
                if value:
                    return value
            except (OSError, ValueError):
                continue
    return None


class UpstoxExecutionClient:
    """Sandbox-first execution boundary aligned with Nautilus ExecutionClient."""

    def __init__(
        self,
        config: UpstoxConfig,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = BASE_URL,
    ) -> None:
        if not config.sandbox:
            raise RuntimeError(
                "refusing to construct a live execution client; sandbox only in this phase"
            )
        self.config = config
        self.base_url = base_url.rstrip("/")
        self._http = http_client or httpx.Client(timeout=30.0)

    # ------------------------------------------------------------------ auth
    def _headers(self) -> dict[str, str]:
        token = _find_sandbox_token()
        if not token:
            raise RuntimeError(
                "missing sandbox token - create a sandbox app at "
                "account.upstox.com/developer/apps#sandbox, click Generate, then "
                "set UPSTOX_SANDBOX_TOKEN (or upstox_sandbox_tokens.json)"
            )
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @staticmethod
    def new_client_order_id() -> str:
        return uuid.uuid4().hex[:16]

    # ------------------------------------------------------------- lifecycle
    async def connect(self) -> None:
        probe = self._http.get(
            f"{self.base_url}/v2/user/profile", headers=self._headers()
        )
        probe.raise_for_status()

    async def submit_order(self, request: SandboxOrderRequest) -> ExecutionReport:
        if request.order_type == OrderType.LIMIT and request.limit_price is None:
            raise ValueError("LIMIT order requires limit_price")
        if request.order_type in (OrderType.SL, OrderType.SL_M) and (
            request.trigger_price is None
        ):
            raise ValueError("SL orders require trigger_price")
        body: dict[str, Any] = {
            "quantity": request.quantity,
            "product": request.product.value,
            "validity": request.validity.value,
            "instrument_token": request.instrument_key,
            "order_type": request.order_type.value,
            "transaction_type": request.side.value,
            "disclosed_quantity": 0,
            "is_amo": False,
            "slice": False,
        }
        if request.limit_price is not None:
            body["price"] = request.limit_price
        if request.trigger_price is not None:
            body["trigger_price"] = request.trigger_price
        if request.tag or request.client_order_id:
            body["tag"] = (request.tag or "")[:20]
        resp = self._http.post(
            f"{self.base_url}/v3/order/place",
            headers=self._headers(),
            json=body,
        )
        return self._report(resp)

    async def modify_order(
        self,
        order_id: str,
        *,
        quantity: int | None = None,
        limit_price: float | None = None,
        order_type: OrderType | None = None,
        validity: Validity | None = None,
    ) -> ExecutionReport:
        body: dict[str, Any] = {"order_id": order_id}
        if quantity is not None:
            body["quantity"] = quantity
        if limit_price is not None:
            body["price"] = limit_price
        if order_type is not None:
            body["order_type"] = order_type.value
        if validity is not None:
            body["validity"] = validity.value
        resp = self._http.put(
            f"{self.base_url}/v3/order/modify",
            headers=self._headers(),
            json=body,
        )
        return self._report(resp)

    async def cancel_order(self, order_id: str) -> ExecutionReport:
        resp = self._http.post(
            f"{self.base_url}/v3/order/cancel/{order_id}",
            headers=self._headers(),
        )
        return self._report(resp)

    # --------------------------------------------------------- reconciliation
    def order_book(self) -> list[dict[str, Any]]:
        resp = self._http.get(
            f"{self.base_url}/v2/order/retrieve-all", headers=self._headers()
        )
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        if isinstance(data, dict) and "orders" in data:
            return list(data["orders"])
        return list(data.values()) if isinstance(data, dict) else list(data)

    def positions(self) -> list[dict[str, Any]]:
        resp = self._http.get(
            f"{self.base_url}/v2/portfolio/short-term-positions",
            headers=self._headers(),
        )
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        if isinstance(data, dict) and "orders" in data:
            return list(data["orders"])
        return list(data.values()) if isinstance(data, dict) else list(data)

    def funds(self) -> dict[str, Any]:
        resp = self._http.get(
            f"{self.base_url}/v2/user/get-funds-and-margin", headers=self._headers()
        )
        resp.raise_for_status()
        return dict((resp.json().get("data") or {}).get("equity") or {})

    async def reconcile(self) -> list[ExecutionReport]:
        """Pull broker order state and rebuild execution reports."""
        reports: list[ExecutionReport] = []
        for order in self.order_book():
            reports.append(
                ExecutionReport(
                    order_id=str(order.get("order_id") or ""),
                    status=str(order.get("status") or ""),
                    filled_qty=int(float(order.get("filled_quantity") or 0)),
                    avg_price=float(order["average_price"]) if order.get("average_price") else None,
                    raw=order,
                )
            )
        return reports

    @staticmethod
    def _report(resp: httpx.Response) -> ExecutionReport:
        if resp.status_code >= 400:
            detail = resp.text[:300]
            raise RuntimeError(f"order endpoint failed ({resp.status_code}): {detail}")
        payload: dict[str, Any] = {}
        with contextlib.suppress(ValueError):
            payload = (resp.json() or {}).get("data") or {}
        if isinstance(payload.get("order_ids"), list) and payload["order_ids"]:
            first_id = str(payload["order_ids"][0])
            return ExecutionReport(order_id=first_id, status="open",
                                   raw=payload)
        status = str(payload.get("status") or "unknown")
        if status.lower() in ("rejected", "rejected_by_broker", "validation_error"):
            raise RuntimeError(f"broker rejected order: {payload}")
        return ExecutionReport(
            order_id=str(payload.get("order_id") or ""),
            status=status,
            filled_qty=int(float(payload.get("filled_quantity") or 0)),
            avg_price=float(payload["average_price"]) if payload.get("average_price") else None,
            raw=payload,
        )


__all__ = [
    "ExecutionReport",
    "OrderSide",
    "OrderType",
    "ProductType",
    "SandboxOrderRequest",
    "Validity",
    "UpstoxExecutionClient",
]
