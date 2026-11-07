"""
Post-Quantum Digital Signatures using NIST ML-DSA.

Every inter-layer message, model weight manifest, and audit entry
is signed to ensure integrity and non-repudiation.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.security.quantum.policy import (
    LAB_FALLBACK_ALGORITHM,
    QuantumSecurityPolicy,
    enforce_pq_availability,
    load_quantum_security_policy,
    log_lab_fallback,
)

logger = logging.getLogger(__name__)

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
    """ML-DSA signing with policy-enforced availability."""

    def __init__(
        self,
        force_algorithm: Optional[str] = None,
        policy: Optional[QuantumSecurityPolicy] = None,
    ) -> None:
        self.policy = policy or load_quantum_security_policy()
        if force_algorithm:
            self._liboqs_mechanism = force_algorithm
            self.algorithm = force_algorithm
        else:
            self._liboqs_mechanism = self.policy.sig_liboqs_name
            self.algorithm = self.policy.sig_fips_name

        self._use_lab_fallback = False
        if _HAS_LIBOQS:
            return

        enforce_pq_availability(self.policy)
        log_lab_fallback("QuantumSigner")
        self._use_lab_fallback = True
        self.algorithm = LAB_FALLBACK_ALGORITHM

    def _pq_active(self) -> bool:
        return _HAS_LIBOQS and not self._use_lab_fallback

    def generate_keypair(self, key_id: Optional[str] = None) -> SigningKeyPair:
        kid = key_id or f"sig-{secrets.token_hex(8)}"

        if self._pq_active():
            sig = oqs.Signature(self._liboqs_mechanism)
            public_key = sig.generate_keypair()
            secret_key = sig.export_secret_key()
            return SigningKeyPair(
                key_id=kid,
                public_key=public_key,
                secret_key=secret_key,
                algorithm=self.policy.sig_fips_name,
            )

        if _HAS_ED25519:
            priv = Ed25519PrivateKey.generate()
            pub = priv.public_key()
            return SigningKeyPair(
                key_id=kid,
                public_key=pub.public_bytes_raw(),
                secret_key=priv.private_bytes_raw(),
                algorithm=LAB_FALLBACK_ALGORITHM,
            )

        seed = secrets.token_bytes(64)
        pub = hashlib.sha256(seed).digest()
        return SigningKeyPair(
            key_id=kid,
            public_key=pub,
            secret_key=seed,
            algorithm=LAB_FALLBACK_ALGORITHM,
        )

    def sign(self, data: bytes, secret_key: bytes) -> bytes:
        """Sign data and return signature bytes."""
        if self._pq_active():
            sig = oqs.Signature(self._liboqs_mechanism, secret_key=secret_key)
            return sig.sign(data)

        if _HAS_ED25519 and self._use_lab_fallback:
            priv = Ed25519PrivateKey.from_private_bytes(secret_key)
            return priv.sign(data)

        return hmac.new(secret_key, data, hashlib.sha512).digest()

    def verify(self, data: bytes, signature: bytes, public_key: bytes) -> bool:
        """Verify a signature. Returns True if valid."""
        try:
            if self._pq_active():
                sig = oqs.Signature(self._liboqs_mechanism)
                return sig.verify(data, signature, public_key)

            if _HAS_ED25519 and self._use_lab_fallback:
                pub = Ed25519PublicKey.from_public_bytes(public_key)
                pub.verify(signature, data)
                return True

            expected = hmac.new(public_key, data, hashlib.sha512).digest()
            return hmac.compare_digest(signature, expected)
        except Exception:
            return False
