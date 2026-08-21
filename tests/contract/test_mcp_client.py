"""MCP client contract tests against a mocked HTTP transport."""

import json

import httpx
import pytest

from indian_quant.ingestion.mcp import McpError, NseBseMcpClient


def mcp_handler(tool_result=None, *, tool_error=False, sse=False):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        method = body.get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": body["id"], "result": {"serverInfo": {"name": "nse-bse-mcp"}}},
                headers={"mcp-session-id": "sess-1"},
            )
        if method == "tools/call":
            result = {
                "content": [{"type": "text", "text": json.dumps(tool_result)}],
                "isError": tool_error,
            }
            payload = {"jsonrpc": "2.0", "id": body["id"], "result": result}
            if sse:
                text = f"event: message\ndata: {json.dumps(payload)}\n\n"
                return httpx.Response(200, text=text, headers={
                    "content-type": "text/event-stream", "mcp-session-id": "sess-1"})
            return httpx.Response(200, json=payload)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body.get("id"), "result": {}})

    return handler


def make_client(handler) -> NseBseMcpClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return NseBseMcpClient("http://localhost:3000/mcp", http_client=http)


class TestMcpClient:
    def test_initialize_and_call_json(self):
        client = make_client(mcp_handler({"data": [{"symbol": "RELIANCE"}]}))
        tools = client.call_tool("nse_equity_historical", {"symbol": "RELIANCE"})
        assert tools["data"][0]["symbol"] == "RELIANCE"
        assert client._session_id == "sess-1"
        client.close()

    def test_sse_framed_response(self):
        client = make_client(
            mcp_handler({"data": [{"close": 100}]}, sse=True)
        )
        out = client.call_tool("nse_equity_historical", {})
        assert out["data"][0]["close"] == 100
        client.close()

    def test_tool_error_raises(self):
        client = make_client(mcp_handler({}, tool_error=True))
        with pytest.raises(McpError):
            client.call_tool("nse_equity_historical", {})
        client.close()

    def test_http_failure_retries_then_raises(self):
        calls = {"n": 0}

        def failing(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            raise httpx.ConnectError("down")

        http = httpx.Client(transport=httpx.MockTransport(failing))
        client = NseBseMcpClient("http://x/mcp", max_retries=2, http_client=http)
        with pytest.raises(McpError):
            client.initialize()
        assert calls["n"] == 2
        client.close()
