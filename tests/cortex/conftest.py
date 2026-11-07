"""Cortex test hooks — lab crypto and XiiD MCP contract fixtures."""

from __future__ import annotations

import importlib
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Iterator

import httpx
import pytest
import uvicorn

from range.mock_xiid_mcp.app import build_mock_server
from range.mock_xiid_mcp.state import MockServerState
from s3m_core.defense.audit.merkle_log import MerkleAuditLog
from src.cortex.tool_map import XiidToolMap
from src.cortex.transport_mcp import MockHttpMCPTransport
from src.cortex.xiid_write_envelope import WriteEnvelope


def _policy_mod():
    return importlib.import_module("src.security.quantum.policy")


@pytest.fixture(autouse=True)
def _lab_mode_without_liboqs(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _policy_mod()
    mod.reset_quantum_policy_cache()
    if not mod.liboqs_available():
        monkeypatch.setenv("S3M_CRYPTO_MODE", "lab")
    yield
    mod.reset_quantum_policy_cache()


@pytest.fixture(scope="session")
def envelope_signing_key() -> bytes:
    return b"s1-range-test-envelope-key-32bytes!"


@pytest.fixture(scope="session")
def mock_bearer_token() -> str:
    return secrets.token_urlsafe(24)


@pytest.fixture(scope="session")
def mock_xiid_server(mock_bearer_token: str) -> Iterator[tuple[str, MockServerState]]:
    """Start streamable-HTTP mock XiiD MCP once per test session."""
    port = 18765
    host = "127.0.0.1"
    _, state, app = build_mock_server(bearer_token=mock_bearer_token, host=host, port=port)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    url = f"http://{host}:{port}/mcp"
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            httpx.get(f"http://{host}:{port}/admin/metrics", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError("mock XiiD MCP server failed to start")

    os.environ.setdefault("XIID_MCP_URL", url)
    yield url, state
    server.should_exit = True


@pytest.fixture
def xiid_mcp_url(mock_xiid_server: tuple[str, MockServerState]) -> str:
    env = os.environ.get("XIID_MCP_URL")
    return env or mock_xiid_server[0]


@pytest.fixture
def mock_server_state(mock_xiid_server: tuple[str, MockServerState]) -> MockServerState:
    return mock_xiid_server[1]


@pytest.fixture
def audit_log(tmp_path: Path) -> MerkleAuditLog:
    return MerkleAuditLog(str(tmp_path / "cortex_audit.jsonl"))


@pytest.fixture
def tool_map() -> XiidToolMap:
    return XiidToolMap.from_yaml()


@pytest.fixture
def mcp_transport(xiid_mcp_url: str, mock_bearer_token: str) -> Iterator[MockHttpMCPTransport]:
    yield MockHttpMCPTransport(xiid_mcp_url, mock_bearer_token)


@pytest.fixture
def approved_envelope(envelope_signing_key: bytes) -> WriteEnvelope:
    return WriteEnvelope.issue(
        operator_id="range-op-1",
        session_id="contract-session",
        action="narrow_route",
        signing_key=envelope_signing_key,
    )
