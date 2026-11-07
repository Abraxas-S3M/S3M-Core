"""Mock XiiD semantics: signed records, idempotency, rollback."""

from __future__ import annotations

import pytest

from src.cortex.transport_mcp import MockHttpMCPTransport


@pytest.mark.asyncio
async def test_write_returns_signed_record_ref(mcp_transport: MockHttpMCPTransport) -> None:
    result = await mcp_transport.call_tool(
        "route.narrow",
        {"route_id": "route-ops", "prefix": "10.60.0.0/28"},
        idempotency_key="signed-1",
    )
    ref = result["signed_record_ref"]
    assert "record_digest" in ref
    assert "signature_b64" in ref


@pytest.mark.asyncio
async def test_idempotency_returns_identical_signed_record(mcp_transport: MockHttpMCPTransport) -> None:
    args = {"route_id": "route-ops", "prefix": "10.60.0.0/29"}
    first = await mcp_transport.call_tool("route.narrow", args, idempotency_key="same-key")
    second = await mcp_transport.call_tool("route.narrow", args, idempotency_key="same-key")
    assert first == second


@pytest.mark.asyncio
async def test_rollback_on_simulated_failure(
    mcp_transport: MockHttpMCPTransport,
    mock_server_state,
) -> None:
    route = mock_server_state.model.find_route("route-perimeter")
    assert route is not None
    original = dict(route)
    mock_server_state.fail_next_write = True
    with pytest.raises(Exception):
        await mcp_transport.call_tool(
            "route.expire",
            {"route_id": "route-perimeter"},
            idempotency_key="rollback-key-perimeter",
        )
    after = mock_server_state.model.find_route("route-perimeter")
    assert after is not None
    assert after["status"] == original["status"]
