"""
Post-Quantum Digital Signatures using NIST ML-DSA (Dilithium-3).

Every inter-layer message, model weight manifest, and audit entry
is signed to ensure integrity and non-repudiation.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

try:
    import oqs
    _HAS_LIBOQS = True
except ImportError:
    oqs = None
    _HAS_LIBOQS = False

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    _HAS_ED25519 = True
except ImportError:
    _HAS_ED25519 = False


@dataclass
class SigningKeyPair:
    """Digital signature keypair with metadata."""
    key_id: str
    public_key: bytes
    secret_key: bytes
    algorithm: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            self.fingerprint = hashlib.sha256(self.public_key).hexdigest()[:16]


class QuantumSigner:
    """ML-DSA (Dilithium-3) signing with Ed25519 / HMAC fallback.

    Priority:
    1. liboqs Dilithium3
    2. Ed25519 (classical, strong)
    3. HMAC-SHA512 (dev/test only)
    """

    DILITHIUM_ALGORITHM = "Dilithium3"

    def __init__(self, force_algorithm: Optional[str] = None) -> None:
        if force_algorithm:
            self.algorithm = force_algorithm
        elif _HAS_LIBOQS:
            self.algorithm = self.DILITHIUM_ALGORITHM
        elif _HAS_ED25519:
            self.algorithm = "Ed25519"
        else:
            self.algorithm = "HMAC-SHA512"

    def generate_keypair(self, key_id: Optional[str] = None) -> SigningKeyPair:
        kid = key_id or f"sig-{secrets.token_hex(8)}"

        if self.algorithm == self.DILITHIUM_ALGORITHM and _HAS_LIBOQS:
            sig = oqs.Signature(self.DILITHIUM_ALGORITHM)
            public_key = sig.generate_keypair()
            secret_key = sig.export_secret_key()
            return SigningKeyPair(
                key_id=kid, public_key=public_key,
                secret_key=secret_key, algorithm=self.DILITHIUM_ALGORITHM,
            )

        if self.algorithm == "Ed25519" and _HAS_ED25519:
            priv = Ed25519PrivateKey.generate()
            pub = priv.public_key()
            return SigningKeyPair(
                key_id=kid, public_key=pub.public_bytes_raw(),
                secret_key=priv.private_bytes_raw(), algorithm="Ed25519",
            )

        seed = secrets.token_bytes(64)
        pub = hashlib.sha256(seed).digest()
        return SigningKeyPair(
            key_id=kid, public_key=pub,
            secret_key=seed, algorithm="HMAC-SHA512",
        )

    def sign(self, data: bytes, secret_key: bytes) -> bytes:
        """Sign data and return signature bytes."""
        if self.algorithm == self.DILITHIUM_ALGORITHM and _HAS_LIBOQS:
            sig = oqs.Signature(self.DILITHIUM_ALGORITHM, secret_key=secret_key)
            return sig.sign(data)

        if self.algorithm == "Ed25519" and _HAS_ED25519:
            priv = Ed25519PrivateKey.from_private_bytes(secret_key)
            return priv.sign(data)

        return hmac.new(secret_key, data, hashlib.sha512).digest()

    def verify(self, data: bytes, signature: bytes, public_key: bytes) -> bool:
        """Verify a signature. Returns True if valid."""
        try:
            if self.algorithm == self.DILITHIUM_ALGORITHM and _HAS_LIBOQS:
                sig = oqs.Signature(self.DILITHIUM_ALGORITHM)
                return sig.verify(data, signature, public_key)

            if self.algorithm == "Ed25519" and _HAS_ED25519:
                pub = Ed25519PublicKey.from_public_bytes(public_key)
                pub.verify(signature, data)
                return True

            expected = hmac.new(public_key, data, hashlib.sha512).digest()
            return hmac.compare_digest(signature, expected)
        except Exception:
            return False
