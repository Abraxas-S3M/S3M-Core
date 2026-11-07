"""
Key persistence backends for mission signing and KEM material.

Tactical context: mission-authority keys must live in customer HSMs in
production; filesystem storage is restricted to lab exercises.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from src.security.quantum.policy import (
    CryptoMode,
    PostQuantumUnavailableError,
    QuantumSecurityPolicy,
    load_quantum_security_policy,
)

MISSION_AUTHORITY_PURPOSE = "mission_authority"


class KeyStorageBackend(ABC):
    """Abstract vault for long-lived signing / KEM secrets."""

    @abstractmethod
    def store_secret(self, key_id: str, purpose: str, secret_bytes: bytes) -> None:
        """Persist secret key material under key_id."""

    @abstractmethod
    def load_secret(self, key_id: str, purpose: str) -> bytes:
        """Load secret key material."""

    @abstractmethod
    def store_public(self, key_id: str, purpose: str, public_bytes: bytes) -> None:
        """Persist public key bytes."""

    @abstractmethod
    def load_public(self, key_id: str, purpose: str) -> bytes:
        """Load public key bytes."""


class FileKeyStorageBackend(KeyStorageBackend):
    """Hex-encoded key files for lab / CI (chmod 600 on secrets)."""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key_id: str, purpose: str, kind: str) -> Path:
        safe = key_id.replace("/", "_")
        return self.base_dir / safe / f"{purpose}_{kind}.key"

    def store_secret(self, key_id: str, purpose: str, secret_bytes: bytes) -> None:
        p = self._path(key_id, purpose, "secret")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(secret_bytes.hex())
        p.chmod(0o600)

    def load_secret(self, key_id: str, purpose: str) -> bytes:
        return bytes.fromhex(self._path(key_id, purpose, "secret").read_text())

    def store_public(self, key_id: str, purpose: str, public_bytes: bytes) -> None:
        p = self._path(key_id, purpose, "public")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(public_bytes.hex())

    def load_public(self, key_id: str, purpose: str) -> bytes:
        return bytes.fromhex(self._path(key_id, purpose, "public").read_text())


class Pkcs11KeyStorageBackend(KeyStorageBackend):
    """Customer HSM integration stub — wire to PKCS#11 module in field builds."""

    def __init__(self, module_path: str = "/usr/lib/libpkcs11.so") -> None:
        self.module_path = module_path

    def store_secret(self, key_id: str, purpose: str, secret_bytes: bytes) -> None:
        raise NotImplementedError(
            f"PKCS#11 backend ({self.module_path}) is a deployment stub; "
            "bind vendor HSM SDK before storing {key_id}/{purpose}"
        )

    def load_secret(self, key_id: str, purpose: str) -> bytes:
        raise NotImplementedError(
            f"PKCS#11 backend ({self.module_path}) is a deployment stub"
        )

    def store_public(self, key_id: str, purpose: str, public_bytes: bytes) -> None:
        raise NotImplementedError("PKCS#11 public key export is HSM-specific")

    def load_public(self, key_id: str, purpose: str) -> bytes:
        raise NotImplementedError("PKCS#11 public key load is HSM-specific")


class KeyStorageError(PermissionError):
    """Policy violation for key material placement."""


def create_key_storage(
    policy: Optional[QuantumSecurityPolicy] = None,
    *,
    backend: Optional[str] = None,
) -> KeyStorageBackend:
    """Factory: select key backend and enforce production signing-key rules."""
    policy = policy or load_quantum_security_policy()
    name = (backend or policy.key_storage_backend).lower()
    if name == "pkcs11":
        return Pkcs11KeyStorageBackend()
    if name == "file":
        return FileKeyStorageBackend(policy.keys_dir)
    raise ValueError(f"Unknown key_storage_backend: {name!r}")


def assert_storage_allowed_for_purpose(
    policy: QuantumSecurityPolicy,
    backend: KeyStorageBackend,
    purpose: str,
) -> None:
    """Reject file-backed storage for mission-authority keys in production."""
    if (
        policy.is_production
        and purpose == MISSION_AUTHORITY_PURPOSE
        and isinstance(backend, FileKeyStorageBackend)
    ):
        raise KeyStorageError(
            "Production policy forbids file backend for mission-authority signing keys; "
            "configure key_storage_backend: pkcs11"
        )
