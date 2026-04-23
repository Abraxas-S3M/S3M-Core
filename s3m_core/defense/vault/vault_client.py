"""Vault client primitives for mission-safe credential access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
import secrets
import threading
import uuid
from typing import Dict, List


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True, frozen=True)
class DynamicCredential:
    """Short-lived credential envelope issued for one tactical task."""

    credential: str
    lease_id: str
    ttl: int
    service: str


@dataclass(slots=True, frozen=True)
class SecretAccess:
    """Audit record showing which session requested which secret path."""

    session_id: str
    path: str
    accessed_at: str
    access_type: str


@dataclass(slots=True)
class _LeaseState:
    credential: str
    service: str
    expires_at: datetime


class VaultClient:
    """Interface layer for Vault-compatible secret stores in S3M."""

    def __init__(
        self,
        vault_addr: str,
        auth_method: str = "approle",
        role_id: str = None,
        tls_cert_path: str = None,
    ) -> None:
        if not vault_addr or not vault_addr.strip():
            raise ValueError("vault_addr must be provided")
        if not auth_method or not auth_method.strip():
            raise ValueError("auth_method must be provided")
        self.vault_addr = vault_addr.strip()
        self.auth_method = auth_method.strip()
        self.role_id = role_id
        self.tls_cert_path = tls_cert_path
        self._lock = threading.RLock()
        self._static_secrets: Dict[str, str] = {}
        self._access_log: List[SecretAccess] = []
        self._active_leases: Dict[str, _LeaseState] = {}

    def __getstate__(self) -> Dict[str, object]:
        state = dict(self.__dict__)
        state.pop("_lock", None)
        return state

    def __setstate__(self, state: Dict[str, object]) -> None:
        self.__dict__.update(state)
        self._lock = threading.RLock()

    def register_secret(self, path: str, value: str) -> None:
        """Registers an offline secret path for edge-runtime operation."""
        if not path or not path.strip():
            raise ValueError("path must be provided")
        if value is None:
            raise ValueError("value must not be None")
        with self._lock:
            self._static_secrets[path.strip()] = value

    def get_secret(self, path: str, session_id: str) -> str:
        """Fetches a secret value and appends a session audit event."""
        if not path or not path.strip():
            raise ValueError("path must be provided")
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be provided")
        normalized_path = path.strip()
        secret_value = self._fetch_secret(normalized_path)
        self.log_access(session_id=session_id.strip(), path=normalized_path, access_type="static_secret")
        return secret_value

    def log_access(self, session_id: str, path: str, access_type: str) -> None:
        """Adds an audit record without ever storing secret values."""
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be provided")
        if not path or not path.strip():
            raise ValueError("path must be provided")
        if not access_type or not access_type.strip():
            raise ValueError("access_type must be provided")
        with self._lock:
            # Tactical context: operators need immutable access trails for incident review.
            self._access_log.append(
                SecretAccess(
                    session_id=session_id.strip(),
                    path=path.strip(),
                    accessed_at=_utc_now().isoformat(),
                    access_type=access_type.strip(),
                )
            )

    def get_dynamic_credential(self, service: str, ttl_seconds: int = 300) -> DynamicCredential:
        """Issues a short-lived credential with lease tracking for revocation."""
        if not service or not service.strip():
            raise ValueError("service must be provided")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._purge_expired_leases()

        lease_id = uuid.uuid4().hex
        credential = secrets.token_urlsafe(32)
        expires_at = _utc_now() + timedelta(seconds=int(ttl_seconds))
        with self._lock:
            self._active_leases[lease_id] = _LeaseState(
                credential=credential,
                service=service.strip(),
                expires_at=expires_at,
            )
        return DynamicCredential(
            credential=credential,
            lease_id=lease_id,
            ttl=int(ttl_seconds),
            service=service.strip(),
        )

    def revoke(self, lease_id: str) -> None:
        """Revokes a dynamic credential lease immediately."""
        if not lease_id or not lease_id.strip():
            raise ValueError("lease_id must be provided")
        with self._lock:
            self._active_leases.pop(lease_id.strip(), None)

    def list_access_log(self, session_id: str) -> List[SecretAccess]:
        """Returns the full secret access audit trail for one session."""
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be provided")
        with self._lock:
            return [entry for entry in self._access_log if entry.session_id == session_id.strip()]

    def _fetch_secret(self, path: str) -> str:
        with self._lock:
            if path in self._static_secrets:
                return self._static_secrets[path]

        env_key = "S3M_VAULT_SECRET_" + path.upper().replace("/", "_").replace("-", "_")
        env_secret = os.getenv(env_key)
        if env_secret is not None:
            return env_secret
        raise KeyError(f"Secret path not found: {path}")

    def _purge_expired_leases(self) -> None:
        now = _utc_now()
        with self._lock:
            expired_ids = [lease_id for lease_id, state in self._active_leases.items() if state.expires_at <= now]
            for lease_id in expired_ids:
                self._active_leases.pop(lease_id, None)
