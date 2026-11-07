"""Transport-layer contract checks (auth, TLS intent, schemas)."""

from __future__ import annotations

import pytest

from src.cortex.manifest import manifest_digest
from src.cortex.transport_mcp import MockHttpMCPTransport, VaultMcpCredentialProvider
from s3m_core.defense.vault import ServiceConfig, VaultClient


@pytest.mark.asyncio
async def test_transport_lists_all_placeholder_tools(mcp_transport: MockHttpMCPTransport) -> None:
    tools = await mcp_transport.list_tools()
    names = {tool["name"] for tool in tools}
    assert "inventory.list_stlinks" in names
    assert "host.quarantine" in names
    digest = manifest_digest(tools)
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_auth_failure_without_bearer(xiid_mcp_url: str) -> None:
    transport = MockHttpMCPTransport(xiid_mcp_url, bearer_token="wrong-token")
    try:
        with pytest.raises(Exception):
            await transport.list_tools()
    finally:
        await transport.close()


def test_audience_resource_binding_enforced() -> None:
    vault = VaultClient(vault_addr="https://vault.local")
    provider = VaultMcpCredentialProvider(
        vault_client=vault,
        service_config=ServiceConfig(
            vault_path="kv/range/xiid/mcp",
            auth_type="bearer",
            header_name="Authorization",
            allowed_endpoints=["http://127.0.0.1:*/mcp"],
        ),
        audience="https://xiid.s3m.range/mcp",
        resource="https://other.example/mcp",
    )
    with pytest.raises(ValueError, match="binding mismatch"):
        provider.validate_binding()
