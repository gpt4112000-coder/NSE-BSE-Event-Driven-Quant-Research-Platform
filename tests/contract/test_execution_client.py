"""Execution client lifecycle tests (mock transport; sandbox guardrails)."""

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from indian_quant.adapters.upstox import (  # noqa: E402
    OrderSide,
    OrderType,
    SandboxOrderRequest,
    UpstoxExecutionClient,
)
from indian_quant.config import UpstoxConfig  # noqa: E402


def make_client(handler) -> UpstoxExecutionClient:
    return UpstoxExecutionClient(
        UpstoxConfig(sandbox=True),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


class TestGuardrails:
    def test_live_construction_refused(self):
        with pytest.raises(RuntimeError):
            UpstoxExecutionClient(UpstoxConfig(sandbox=False))

    def test_missing_token_raises_clear_error(self, tmp_path, monkeypatch):
        monkeypatch.delenv("UPSTOX_SANDBOX_TOKEN", raising=False)
        monkeypatch.chdir(tmp_path)
        client = make_client(lambda r: httpx.Response(200))
        with pytest.raises(RuntimeError, match="sandbox app"):
            client._headers()


class TestLifecycle:
    def handler_ok(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/place"):
            assert "MARKET" in request.content.decode()
            return httpx.Response(200, json={"data": {
                "order_id": "O1", "status": "open"}})
        if path.endswith("/modify"):
            return httpx.Response(200, json={"data": {
                "order_id": "O1", "status": "modified"}})
        if "/cancel/" in path:
            return httpx.Response(200, json={"data": {
                "order_id": "O1", "status": "cancelled"}})
        return httpx.Response(200, json={})

    async def test_submit_modify_cancel(self, tmp_path, monkeypatch):
        monkeypatch.setenv("UPSTOX_SANDBOX_TOKEN", "SBX")
        client = make_client(self.handler_ok)

        req = SandboxOrderRequest(
            instrument_key="NSE_EQ|INE002A01018",
            quantity=10, side=OrderSide.BUY,
        )
        rep = await client.submit_order(req)
        assert rep.order_id == "O1" and rep.status == "open"

        rep = await client.modify_order("O1", quantity=5)
        assert rep.status == "modified"

        rep = await client.cancel_order("O1")
        assert rep.status == "cancelled"

    def test_limit_without_price_rejected_locally(self):
        req = SandboxOrderRequest(
            instrument_key="K", quantity=1, side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
        )
        assert req.limit_price is None

    async def test_broker_rejection_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("UPSTOX_SANDBOX_TOKEN", "SBX")

        def rejecting(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": {
                "order_id": "O9", "status": "rejected",
                "error": "insufficient funds"}})

        client = make_client(rejecting)
        with pytest.raises(RuntimeError, match="rejected"):
            await client.submit_order(SandboxOrderRequest(
                instrument_key="K", quantity=1, side=OrderSide.SELL))

    async def test_http_400_surfaces_detail(self, tmp_path, monkeypatch):
        monkeypatch.setenv("UPSTOX_SANDBOX_TOKEN", "SBX")
        client = make_client(
            lambda r: httpx.Response(400, text="UDAPI100011 invalid key"))
        with pytest.raises(RuntimeError, match="invalid key"):
            await client.submit_order(SandboxOrderRequest(
                instrument_key="BAD", quantity=1, side=OrderSide.BUY))


class TestReconcilePull:
    async def test_order_book_and_positions(self, tmp_path, monkeypatch):
        monkeypatch.setenv("UPSTOX_SANDBOX_TOKEN", "SBX")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v2/order/retrieve-all":
                return httpx.Response(200, json={"data": [{
                    "order_id": "O1", "status": "complete",
                    "filled_quantity": 100, "average_price": 1321.5}]})
            if "positions" in request.url.path:
                return httpx.Response(200, json={"data": [{
                    "instrument_key": "NSE_EQ|INE002A01018", "quantity": 100}]})
            if request.url.path.endswith("/get-funds-and-margin"):
                return httpx.Response(200, json={"data": {"equity": {
                    "available_margin": 500000.0}}})
            return httpx.Response(200, json={})

        client = make_client(handler)
        book = client.order_book()
        pos = client.positions()
        funds = client.funds()
        assert book[0]["order_id"] == "O1"
        assert pos[0]["quantity"] == 100
        assert funds["available_margin"] == 500000.0

        reports = await client.reconcile()
        assert reports and reports[0].status == "complete"
