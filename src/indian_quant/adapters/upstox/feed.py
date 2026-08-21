"""Upstox Market Data Feed V3 WebSocket client (Phase 6 scaffold).

Protocol: wss + protobuf binary frames. Modes: ltpc, option_greeks, full,
full_d30. Full decoding requires the generated protobuf classes from the
official ``upstox-python-sdk`` feed schema; this module owns connection
lifecycle, subscription management and frame dispatch, and delegates
binary decoding to a pluggable FeedDecoder so the strategy-facing surface
is already stable.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from indian_quant.config.settings import UpstoxConfig


class FeedDecoder:
    """Pluggable protobuf decoder. Implement decode() against generated classes."""

    def decode(self, payload: bytes) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "wire up generated Upstox protobuf classes here "
            "(see docs/adapter.md, Phase 6)"
        )


class JsonFeedDecoder(FeedDecoder):
    def decode(self, payload: bytes) -> list[dict[str, Any]]:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return []
        return [data] if isinstance(data, dict) else [d for d in data if isinstance(d, dict)]


class UpstoxFeedClient:
    def __init__(
        self,
        config: UpstoxConfig,
        *,
        decoder: FeedDecoder | None = None,
        on_records: Callable[[list[dict[str, Any]]], Awaitable[None]] | None = None,
    ) -> None:
        self.config = config
        self.decoder = decoder or FeedDecoder()
        self.on_records = on_records
        self._ws = None
        self._connected = False

    async def _authorize_url(self) -> str:
        token = self.config.resolve_token()
        if not token:
            raise RuntimeError(
                f"missing access token; set {self.config.access_token_env} env var"
            )
        return f"{self.config.ws_url}?authorization={token}"

    async def connect(self) -> None:
        import websockets  # optional dependency at runtime

        url = await self._authorize_url()
        self._ws = await websockets.connect(url)
        self._connected = True

    async def subscribe(self, instrument_keys: list[str], mode: str = "ltpc") -> None:
        if not self._connected or self._ws is None:
            raise RuntimeError("feed not connected")
        message = {"guid": "indian-quant", "method": "sub", "data": {
            "mode": mode,
            "instrumentKeys": instrument_keys,
        }}
        await self._ws.send(json.dumps(message))

    async def run(self) -> None:
        if not self._connected or self._ws is None:
            raise RuntimeError("feed not connected")
        async for raw in self._ws:
            if isinstance(raw, str):
                raw = raw.encode()
            records = self.decoder.decode(raw)
            if records and self.on_records:
                await self.on_records(records)

    async def disconnect(self) -> None:
        if self._ws is not None:
            await self._ws.close()
        self._connected = False

    @staticmethod
    def authorize_header_probe(config: UpstoxConfig) -> dict[str, str]:
        token = config.resolve_token()
        if not token:
            raise RuntimeError(f"set {config.access_token_env}")
        resp = httpx.get("https://api.upstox.com/v2/user/profile", headers={
            "Authorization": f"Bearer {token}", "Accept": "application/json",
        })
        resp.raise_for_status()
        return dict(resp.json())


async def stream_once(config: UpstoxConfig, seconds: float = 5.0) -> int:
    """Smoke-run the feed for a few seconds; returns number of decoded records."""
    received = 0

    async def on_records(records: list[dict[str, Any]]) -> None:
        nonlocal received
        received += len(records)

    client = UpstoxFeedClient(config, decoder=JsonFeedDecoder(), on_records=on_records)
    await asyncio.wait_for(client.run(), timeout=seconds)
    return received
