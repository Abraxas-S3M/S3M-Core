"""Contract tests for XiidMCPBroker against the S1 range mock (or XIID_MCP_URL)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from range.mock_xiid_mcp.state import MockServerState
from src.cortex.xiid_broker import EnvelopeRequired, ManifestPinMismatch, XiidMCPBroker
from src.cortex.xiid_write_envelope import WriteEnvelope
from src.cortex.tool_map import XiidToolMap
from src.cortex.transport_mcp import MockHttpMCPTransport
from s3m_core.defense.audit.merkle_log import MerkleAuditLog


def _broker(
    transport: MockHttpMCPTransport,
    audit_log: MerkleAuditLog,
    tool_map: XiidToolMap,
    envelope_signing_key: bytes,
) -> XiidMCPBroker:
    return XiidMCPBroker(
        transport=transport,
        tool_map=tool_map,
        audit_log=audit_log,
        session_id="contract-session",
        envelope_signing_key=envelope_signing_key,
    )


@pytest.mark.asyncio
async def test_broker_pins_manifest_digest(
    mcp_transport: MockHttpMCPTransport,
    audit_log: MerkleAuditLog,
    tool_map: XiidToolMap,
    envelope_signing_key: bytes,
) -> None:
    broker = _broker(mcp_transport, audit_log, tool_map, envelope_signing_key)
    digest = await broker.connect_and_pin_manifest()
    assert len(digest) == 64
    assert broker.manifest_digest == digest


@pytest.mark.asyncio
async def test_rug_pull_makes_broker_refuse(
    mcp_transport: MockHttpMCPTransport,
    audit_log: MerkleAuditLog,
    tool_map: XiidToolMap,
    envelope_signing_key: bytes,
    mock_server_state: MockServerState,
    xiid_mcp_url: str,
) -> None:
    broker = _broker(mcp_transport, audit_log, tool_map, envelope_signing_key)
    await broker.connect_and_pin_manifest()
    base_url = xiid_mcp_url.removesuffix("/mcp")
    httpx.post(f"{base_url}/admin/rug-pull", json={"tool_name": "route.narrow"})
    with pytest.raises(ManifestPinMismatch):
        await broker.invoke("list_stlinks")
    assert mock_server_state.rug_pulled_tool == "route.narrow"


@pytest.mark.asyncio
async def test_write_without_envelope_denied(
    mcp_transport: MockHttpMCPTransport,
    audit_log: MerkleAuditLog,
    tool_map: XiidToolMap,
    envelope_signing_key: bytes,
    mock_server_state: MockServerState,
    xiid_mcp_url: str,
) -> None:
    broker = _broker(mcp_transport, audit_log, tool_map, envelope_signing_key)
    await broker.connect_and_pin_manifest()
    before = dict(mock_server_state.metrics.tool_calls)
    with pytest.raises(EnvelopeRequired):
        await broker.invoke("narrow_route", {"route_id": "route-perimeter", "prefix": "10.50.0.0/28"})
    base_url = xiid_mcp_url.removesuffix("/mcp")
    metrics = httpx.get(f"{base_url}/admin/metrics").json()
    assert metrics["tool_calls"].get("route.narrow", 0) == before.get("route.narrow", 0)


@pytest.mark.asyncio
async def test_approved_write_idempotent_single_mock_execution(
    mcp_transport: MockHttpMCPTransport,
    audit_log: MerkleAuditLog,
    tool_map: XiidToolMap,
    envelope_signing_key: bytes,
    approved_envelope: WriteEnvelope,
    mock_server_state: MockServerState,
    xiid_mcp_url: str,
) -> None:
    broker = _broker(mcp_transport, audit_log, tool_map, envelope_signing_key)
    await broker.connect_and_pin_manifest()
    args = {"route_id": "route-perimeter", "prefix": "10.50.0.0/28"}
    key = "idem-narrow-001"
    await broker.invoke("narrow_route", args, envelope=approved_envelope, idempotency_key=key)
    await broker.invoke("narrow_route", args, envelope=approved_envelope, idempotency_key=key)
    base_url = xiid_mcp_url.removesuffix("/mcp")
    metrics = httpx.get(f"{base_url}/admin/metrics").json()
    assert metrics["tool_calls"]["route.narrow"] == 2
    assert metrics["write_calls"] == 1
    route = mock_server_state.model.find_route("route-perimeter")
    assert route is not None
    assert route["narrow_to"] == "10.50.0.0/28"


@pytest.mark.asyncio
async def test_evidence_chain_verifies(
    mcp_transport: MockHttpMCPTransport,
    audit_log: MerkleAuditLog,
    tool_map: XiidToolMap,
    envelope_signing_key: bytes,
    approved_envelope: WriteEnvelope,
) -> None:
    broker = _broker(mcp_transport, audit_log, tool_map, envelope_signing_key)
    await broker.connect_and_pin_manifest()
    await broker.invoke(
        "narrow_route",
        {"route_id": "route-perimeter", "prefix": "10.50.0.0/27"},
        envelope=approved_envelope,
        idempotency_key="idem-evidence-1",
    )
    assert broker.verify_evidence_chain() is True
