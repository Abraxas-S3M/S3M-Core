"""Credential proxy that executes authenticated calls outside agent memory."""

from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
import multiprocessing as mp
from typing import Dict, List, Mapping, Optional
import urllib.error
import urllib.request

from .vault_client import DynamicCredential, VaultClient


@dataclass(slots=True, frozen=True)
class ServiceConfig:
    """Per-service credential and endpoint policy for proxy enforcement."""

    vault_path: str
    auth_type: str
    header_name: str
    allowed_endpoints: List[str] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class ProxyResponse:
    """Sanitized proxy response returned to the requesting agent session."""

    status_code: int
    headers: Dict[str, str]
    body: str
    credential_used: bool


def _proxy_worker(
    method: str,
    path: str,
    body: Optional[str],
    headers: Dict[str, str],
    connection: mp.connection.Connection,
) -> None:
    try:
        encoded_body = body.encode("utf-8") if body is not None else None
        request = urllib.request.Request(url=path, data=encoded_body, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = {
                "status_code": int(response.getcode()),
                "headers": {key: value for key, value in response.headers.items()},
                "body": response.read().decode("utf-8", errors="replace"),
            }
            connection.send(payload)
    except urllib.error.HTTPError as error:
        payload = {
            "status_code": int(error.code),
            "headers": {key: value for key, value in error.headers.items()},
            "body": error.read().decode("utf-8", errors="replace"),
        }
        connection.send(payload)
    except Exception as error:  # pragma: no cover - defensive transport guard.
        connection.send({"error": str(error)})
    finally:
        connection.close()


class CredentialProxy:
    """Executes authenticated HTTP operations in a hardened proxy process."""

    def __init__(self, vault_client: VaultClient, allowed_services: Dict[str, ServiceConfig]) -> None:
        if vault_client is None:
            raise ValueError("vault_client must be provided")
        self.vault_client = vault_client
        self.allowed_services: Dict[str, ServiceConfig] = {}
        for service_name, config in allowed_services.items():
            self.allowed_services[service_name] = self._normalize_service_config(config)
        self._request_timeout_seconds = 20

    def proxy_request(
        self,
        session_id: str,
        service: str,
        method: str,
        path: str,
        body: str = None,
        headers: Dict[str, str] = None,
    ) -> ProxyResponse:
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be provided")
        if not service or not service.strip():
            raise ValueError("service must be provided")
        if not method or not method.strip():
            raise ValueError("method must be provided")
        if not path or not path.strip():
            raise ValueError("path must be provided")

        config = self._require_service(service.strip())
        self._validate_endpoint(path=path.strip(), allowed_endpoints=config.allowed_endpoints)
        request_headers = self._normalize_headers(headers)

        dynamic_credential: DynamicCredential | None = None
        try:
            dynamic_credential = self.vault_client.get_dynamic_credential(service=service.strip(), ttl_seconds=300)
            auth_value = self._build_auth_header(auth_type=config.auth_type, credential=dynamic_credential.credential)
            request_headers[config.header_name] = auth_value

            raw_response = self._execute_in_proxy_process(
                method=method.strip().upper(),
                path=path.strip(),
                body=body,
                headers=request_headers,
            )
            sanitized_headers, sanitized_body = self._sanitize_response(
                headers=raw_response["headers"],
                body=raw_response["body"],
                credential=dynamic_credential.credential,
                auth_header=config.header_name,
            )
            return ProxyResponse(
                status_code=int(raw_response["status_code"]),
                headers=sanitized_headers,
                body=sanitized_body,
                credential_used=True,
            )
        finally:
            if dynamic_credential is not None:
                # Tactical context: revoke credentials immediately to shrink breach window.
                self.vault_client.revoke(dynamic_credential.lease_id)

    def get_available_services(self) -> List[str]:
        return sorted(self.allowed_services.keys())

    def _require_service(self, service: str) -> ServiceConfig:
        if service not in self.allowed_services:
            raise PermissionError(f"Service '{service}' is not allowed for proxy access")
        return self.allowed_services[service]

    def _normalize_service_config(self, config: ServiceConfig | Mapping[str, object]) -> ServiceConfig:
        if isinstance(config, ServiceConfig):
            candidate = config
        elif isinstance(config, Mapping):
            candidate = ServiceConfig(
                vault_path=str(config.get("vault_path", "")),
                auth_type=str(config.get("auth_type", "")),
                header_name=str(config.get("header_name", "")),
                allowed_endpoints=[str(endpoint) for endpoint in config.get("allowed_endpoints", [])],
            )
        else:
            raise TypeError("allowed_services values must be ServiceConfig or mapping")

        if not candidate.vault_path.strip():
            raise ValueError("ServiceConfig.vault_path must be provided")
        if candidate.auth_type not in {"bearer", "basic", "api_key"}:
            raise ValueError("ServiceConfig.auth_type must be bearer, basic, or api_key")
        if not candidate.header_name.strip():
            raise ValueError("ServiceConfig.header_name must be provided")
        if not candidate.allowed_endpoints:
            raise ValueError("ServiceConfig.allowed_endpoints must include at least one endpoint")
        return ServiceConfig(
            vault_path=candidate.vault_path.strip(),
            auth_type=candidate.auth_type,
            header_name=candidate.header_name.strip(),
            allowed_endpoints=[endpoint.strip() for endpoint in candidate.allowed_endpoints if endpoint.strip()],
        )

    def _validate_endpoint(self, path: str, allowed_endpoints: List[str]) -> None:
        for endpoint_pattern in allowed_endpoints:
            if fnmatch.fnmatch(path, endpoint_pattern):
                return
        raise PermissionError(f"Path '{path}' is not allowed for proxy access")

    def _normalize_headers(self, headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        if headers is None:
            return {}
        normalized: Dict[str, str] = {}
        for key, value in headers.items():
            if key and value is not None:
                normalized[str(key)] = str(value)
        return normalized

    def _build_auth_header(self, auth_type: str, credential: str) -> str:
        if auth_type == "bearer":
            return f"Bearer {credential}"
        if auth_type == "basic":
            return f"Basic {credential}"
        if auth_type == "api_key":
            return credential
        raise ValueError(f"Unsupported auth_type: {auth_type}")

    def _execute_in_proxy_process(
        self, method: str, path: str, body: Optional[str], headers: Dict[str, str]
    ) -> Dict[str, object]:
        context = mp.get_context("spawn")
        parent_conn, child_conn = context.Pipe(duplex=False)
        process = context.Process(target=_proxy_worker, args=(method, path, body, headers, child_conn), daemon=True)
        process.start()
        child_conn.close()
        process.join(timeout=self._request_timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)
            raise TimeoutError("Proxy request timed out in hardened process")
        if not parent_conn.poll():
            raise RuntimeError("Proxy process exited without returning a response")
        payload = parent_conn.recv()
        if "error" in payload:
            raise RuntimeError(f"Proxy process failed: {payload['error']}")
        return payload

    def _sanitize_response(
        self, headers: Mapping[str, str], body: str, credential: str, auth_header: str
    ) -> tuple[Dict[str, str], str]:
        auth_header_lower = auth_header.lower()
        sanitized_headers: Dict[str, str] = {}
        for key, value in headers.items():
            lower_key = key.lower()
            if lower_key in {auth_header_lower, "authorization", "proxy-authorization"}:
                continue
            sanitized_headers[key] = str(value).replace(credential, "[REDACTED]")
        return sanitized_headers, body.replace(credential, "[REDACTED]")
