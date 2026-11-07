"""Canonical signing helpers for approver devices (Ed25519, edge-safe)."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from typing import Any, Dict

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def generate_device_keypair() -> tuple[bytes, bytes]:
    """Generate device-held Ed25519 key material (private, public)."""
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    return private.private_bytes_raw(), public.public_bytes_raw()


def canonical_approval_payload(
    *,
    change_id: str,
    envelope_id: str,
    decision: str,
    timestamp: str,
    nonce: str,
) -> bytes:
    """Stable payload bytes the device must sign (anti-replay via nonce)."""
    body: Dict[str, Any] = {
        "change_id": change_id,
        "envelope_id": envelope_id,
        "decision": decision.upper(),
        "timestamp": timestamp,
        "nonce": nonce,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_payload(private_key: bytes, payload: bytes) -> str:
    priv = Ed25519PrivateKey.from_private_bytes(private_key)
    sig = priv.sign(payload)
    return base64.b64encode(sig).decode("ascii")


def verify_payload(public_key: bytes, payload: bytes, signature_b64: str) -> bool:
    try:
        sig = base64.b64decode(signature_b64.encode("ascii"))
        pub = Ed25519PublicKey.from_public_bytes(public_key)
        pub.verify(sig, payload)
        return True
    except Exception:
        return False


def hash_duress_pin(pin: str, salt: str) -> str:
    """Salted SHA-256 for duress PIN storage (server never stores plaintext)."""
    digest = hashlib.sha256(f"{salt}:{pin}".encode("utf-8")).hexdigest()
    return digest


def new_salt() -> str:
    return secrets.token_hex(16)


def new_nonce() -> str:
    return secrets.token_hex(16)
