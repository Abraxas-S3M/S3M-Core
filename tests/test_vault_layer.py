"""Unit tests for S3M credential vault layer."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading

import pytest

from s3m_core.defense.vault import (
    CredentialProxy,
    ServiceConfig,
    TokenManager,
    VaultClient,
)


class _EchoAuthHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length).decode("utf-8", errors="replace")
        response_body = json.dumps(
            {
                "authorization": self.headers.get("Authorization", ""),
                "body": body,
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Authorization", self.headers.get("Authorization", ""))
        self.end_headers()
        self.wfile.write(response_body.encode("utf-8"))

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - framework signature
        return


def _start_server() -> tuple[HTTPServer, threading.Thread]:
    server = HTTPServer(("127.0.0.1", 0), _EchoAuthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_vault_client_records_access_without_secret_value_in_audit_log() -> None:
    vault = VaultClient(vault_addr="https://vault.local")
    vault.register_secret(path="kv/tactical/api", value="mission-sensitive-value")

    fetched = vault.get_secret(path="kv/tactical/api", session_id="session-alpha")

    assert fetched == "mission-sensitive-value"
    access_log = vault.list_access_log("session-alpha")
    assert len(access_log) == 1
    assert access_log[0].path == "kv/tactical/api"
    assert access_log[0].access_type == "static_secret"
    assert "mission-sensitive-value" not in repr(access_log[0])


def test_credential_proxy_runs_authenticated_request_and_sanitizes_echo() -> None:
    server, thread = _start_server()
    port = server.server_port

    vault = VaultClient(vault_addr="https://vault.local")
    proxy = CredentialProxy(
        vault_client=vault,
        allowed_services={
            "intel_api": ServiceConfig(
                vault_path="kv/tactical/intel-api",
                auth_type="bearer",
                header_name="Authorization",
                allowed_endpoints=[f"http://127.0.0.1:{port}/v1/*"],
            )
        },
    )

    try:
        response = proxy.proxy_request(
            session_id="session-bravo",
            service="intel_api",
            method="POST",
            path=f"http://127.0.0.1:{port}/v1/data",
            body='{"msg":"hello"}',
            headers={"Content-Type": "application/json"},
        )
    finally:
        server.shutdown()
        thread.join(timeout=3)

    assert response.status_code == 200
    assert response.credential_used is True
    assert "Bearer [REDACTED]" in response.body
    assert "Authorization" not in response.headers
    access_log = vault.list_access_log("session-bravo")
    assert len(access_log) == 1
    assert access_log[0].path == "kv/tactical/intel-api"
    assert access_log[0].access_type == "proxy_dynamic_credential"


def test_credential_proxy_enforces_service_and_endpoint_allow_list() -> None:
    vault = VaultClient(vault_addr="https://vault.local")

    proxy = CredentialProxy(
        vault_client=vault,
        allowed_services={
            "ops_api": ServiceConfig(
                vault_path="kv/tactical/ops-api",
                auth_type="api_key",
                header_name="X-API-Key",
                allowed_endpoints=["http://127.0.0.1:9000/allowed/*"],
            )
        },
    )

    with pytest.raises(PermissionError, match="Service"):
        proxy.proxy_request(
            session_id="session-charlie",
            service="unknown_service",
            method="GET",
            path="http://127.0.0.1:9000/allowed/resource",
        )

    with pytest.raises(PermissionError, match="Path"):
        proxy.proxy_request(
            session_id="session-charlie",
            service="ops_api",
            method="GET",
            path="http://127.0.0.1:9000/blocked/resource",
        )


def test_token_manager_issue_validate_and_revoke_flows() -> None:
    vault = VaultClient(vault_addr="https://vault.local")
    manager = TokenManager(vault_client=vault, default_ttl=120)

    issued = manager.issue_token(
        session_id="session-delta",
        allowed_services=["intel_api", "ops_api"],
        ttl=30,
    )
    validated = manager.validate_token(issued.token)
    assert validated.valid is True
    assert validated.session_id == "session-delta"
    assert validated.remaining_ttl > 0
    assert validated.allowed_services == ["intel_api", "ops_api"]

    manager.revoke_token(issued.token)
    after_revoke = manager.validate_token(issued.token)
    assert after_revoke.valid is False

    first = manager.issue_token("session-delta", ["intel_api"], ttl=30)
    second = manager.issue_token("session-delta", ["ops_api"], ttl=30)
    manager.revoke_all_for_session("session-delta")

    assert manager.validate_token(first.token).valid is False
    assert manager.validate_token(second.token).valid is False
