"""Streamable-HTTP MCP client transport for the Cortex XiiD broker."""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Protocol, runtime_checkable

import httpx2
import mcp_types as types
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import MCP_DEFAULT_TIMEOUT, create_mcp_http_client

from s3m_core.defense.vault.credential_proxy import ServiceConfig
from s3m_core.defense.vault.vault_client import DynamicCredential, VaultClient

logger = logging.getLogger(__name__)

VAULT_SERVICE = "xiid_mcp"
REDACTED = "[REDACTED]"


def _build_auth_header(credential: str) -> str:
    return f"Bearer {credential}"


def _sanitize_for_logs(value: str, credential: str) -> str:
    if not credential:
        return value
    return value.replace(credential, REDACTED)


@runtime_checkable
class MCPTransport(Protocol):
    """Broker-facing MCP transport contract."""

    async def list_tools(self) -> List[Dict[str, Any]]:
        ...

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...

    async def close(self) -> None:
        ...


@dataclass(slots=True)
class McpTransportConfig:
    """Connection settings loaded from configs/cortex.yaml."""

    url: str
    oauth_audience: str
    oauth_resource: str
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 60.0
    max_retries: int = 3
    retry_backoff_seconds: float = 0.25
    vault_path: str = "kv/range/xiid/mcp"
    service_name: str = VAULT_SERVICE


class VaultMcpCredentialProvider:
    """Issues short-lived OAuth bearer tokens via the vault credential model.

    Tactical context: tokens never enter model context or application logs.
    """

    def __init__(
        self,
        vault_client: VaultClient,
        service_config: ServiceConfig,
        *,
        audience: str,
        resource: str,
    ) -> None:
        self._vault = vault_client
        self._service_config = service_config
        self._audience = audience.strip()
        self._resource = resource.strip()

    def acquire(self, session_id: str) -> DynamicCredential:
        if not session_id.strip():
            raise ValueError("session_id is required")
        credential = self._vault.get_dynamic_credential(service=VAULT_SERVICE, ttl_seconds=300)
        self._vault.log_access(
            session_id=session_id.strip(),
            path=self._service_config.vault_path,
            access_type="mcp_bearer",
        )
        return credential

    def release(self, lease_id: str) -> None:
        self._vault.revoke(lease_id)

    def validate_binding(self) -> None:
        if not self._audience or not self._resource:
            raise ValueError("oauth audience and resource must be configured")
        if self._audience != self._resource:
            raise ValueError("oauth audience/resource binding mismatch")


class HttpMCPTransport(MCPTransport):
    """Production MCP transport over streamable HTTP with vault-backed auth."""

    def __init__(
        self,
        config: McpTransportConfig,
        credential_provider: VaultMcpCredentialProvider,
        *,
        session_id: str,
        verify_tls: bool = True,
    ) -> None:
        self._config = config
        self._credential_provider = credential_provider
        self._session_id = session_id
        self._verify_tls = verify_tls
        self._client: Client | None = None
        self._http_client: httpx2.AsyncClient | None = None
        self._credential_lease: Optional[str] = None
        self._active_token: str = ""

    @property
    def url(self) -> str:
        return self._config.url

    async def _open(self) -> Client:
        if self._client is not None:
            return self._client
        self._credential_provider.validate_binding()
        issued = self._credential_provider.acquire(self._session_id)
        self._credential_lease = issued.lease_id
        self._active_token = issued.credential
        timeout = httpx2.Timeout(
            self._config.connect_timeout_seconds,
            read=self._config.read_timeout_seconds,
        )
        headers = {
            self._service_config_header(): _build_auth_header(issued.credential),
            "MCP-Resource": self._config.oauth_resource,
        }
        ssl_context = ssl.create_default_context() if self._verify_tls else False
        self._http_client = create_mcp_http_client(headers=headers, timeout=timeout)
        if self._verify_tls:
            self._http_client = httpx2.AsyncClient(
                headers=headers,
                timeout=timeout,
                verify=ssl_context,
            )
        transport = streamable_http_client(self._config.url, http_client=self._http_client)
        self._client = Client(
            transport,
            read_timeout_seconds=self._config.read_timeout_seconds,
            mode="legacy",
        )
        await self._client.__aenter__()
        return self._client

    def _service_config_header(self) -> str:
        return "Authorization"

    async def list_tools(self) -> List[Dict[str, Any]]:
        client = await self._open()
        result = await client.list_tools()
        tools = []
        for tool in result.tools:
            schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {}
            if hasattr(schema, "model_dump"):
                schema = schema.model_dump()
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": schema,
                }
            )
        return tools

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        client = await self._open()
        args = dict(arguments or {})
        if idempotency_key:
            args.setdefault("idempotency_key", idempotency_key)

        attempt = 0
        last_error: Exception | None = None
        while attempt <= self._config.max_retries:
            try:
                result = await client.call_tool(name, args)
                if getattr(result, "is_error", False) or getattr(result, "isError", False):
                    payload = _tool_result_to_dict(result)
                    raise RuntimeError(str(payload.get("content", "tool call failed")))
                return _tool_result_to_dict(result)
            except RuntimeError:
                raise
            except Exception as exc:  # pragma: no cover - selective retry
                last_error = exc
                msg = _sanitize_for_logs(str(exc), self._active_token)
                logger.warning("MCP call_tool retry for %s (%s)", name, msg)
                attempt += 1
                if attempt > self._config.max_retries:
                    break
                await asyncio.sleep(self._config.retry_backoff_seconds * attempt)
        assert last_error is not None
        raise last_error

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception:
                pass
            self._client = None
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
        if self._credential_lease:
            self._credential_provider.release(self._credential_lease)
            self._credential_lease = None
            self._active_token = ""

class MockHttpMCPTransport(HttpMCPTransport):
    """Test transport that pins a static bearer without vault round-trips."""

    def __init__(self, url: str, bearer_token: str, *, verify_tls: bool = False) -> None:
        config = McpTransportConfig(
            url=url,
            oauth_audience="https://xiid.s3m.range/mcp",
            oauth_resource="https://xiid.s3m.range/mcp",
        )
        vault = VaultClient(vault_addr="https://vault.local")
        provider = VaultMcpCredentialProvider(
            vault_client=vault,
            service_config=ServiceConfig(
                vault_path="kv/range/xiid/mcp",
                auth_type="bearer",
                header_name="Authorization",
                allowed_endpoints=[url.rstrip("/") + "/*"],
            ),
            audience=config.oauth_audience,
            resource=config.oauth_resource,
        )
        super().__init__(config, provider, session_id="mock-session", verify_tls=verify_tls)
        self._static_bearer = bearer_token

    def acquire_token_override(self) -> None:
        self._active_token = self._static_bearer
        self._credential_lease = "static"

    async def _open(self) -> Client:
        if self._client is not None:
            return self._client
        self._credential_provider.validate_binding()
        self._active_token = self._static_bearer
        timeout = httpx2.Timeout(MCP_DEFAULT_TIMEOUT, read=self._config.read_timeout_seconds)
        headers = {
            "Authorization": _build_auth_header(self._static_bearer),
            "MCP-Resource": self._config.oauth_resource,
        }
        self._http_client = httpx2.AsyncClient(headers=headers, timeout=timeout, verify=False)
        transport = streamable_http_client(self._config.url, http_client=self._http_client)
        self._client = Client(
            transport,
            read_timeout_seconds=self._config.read_timeout_seconds,
            mode="legacy",
        )
        await self._client.__aenter__()
        return self._client

    def release(self, lease_id: str) -> None:  # type: ignore[override]
        return


def _tool_result_to_dict(result: types.CallToolResult) -> Dict[str, Any]:
    structured = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
    if structured is not None:
        if isinstance(structured, Mapping):
            return _unwrap_tool_payload(dict(structured))
        return {"value": structured}
    text_chunks = [block.text for block in result.content if getattr(block, "text", None)]
    if len(text_chunks) == 1:
        import json

        try:
            parsed = json.loads(text_chunks[0])
            if isinstance(parsed, dict):
                return _unwrap_tool_payload(parsed)
        except json.JSONDecodeError:
            pass
    return {"content": text_chunks, "is_error": bool(getattr(result, "isError", getattr(result, "is_error", False)))}


def _unwrap_tool_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    nested = payload.get("result")
    if isinstance(nested, dict):
        return dict(nested)
    return payload
