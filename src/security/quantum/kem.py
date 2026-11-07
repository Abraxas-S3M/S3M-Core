"""
Post-Quantum Key Encapsulation using NIST ML-KEM.

Uses oqs-python (liboqs) when available; lab mode allows labeled fallbacks only.
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
    PostQuantumUnavailableError,
    QuantumSecurityPolicy,
    enforce_pq_availability,
    liboqs_available,
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
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey,
        X25519PublicKey,
    )
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    _HAS_X25519 = True
except ImportError:
    _HAS_X25519 = False


@dataclass
class KEMKeyPair:
    """Post-quantum KEM keypair with metadata."""

    key_id: str
    public_key: bytes
    secret_key: bytes  # NEVER leaves the generating node
    algorithm: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.fingerprint:
            self.fingerprint = hashlib.sha256(self.public_key).hexdigest()[:16]


@dataclass
class EncapsulatedKey:
    """Result of KEM encapsulation: ciphertext + shared secret."""

    ciphertext: bytes
    shared_secret: bytes
    algorithm: str
    sender_fingerprint: str = ""


class QuantumKEM:
    """ML-KEM key encapsulation under configured security policy."""

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
            self._liboqs_mechanism = self.policy.kem_liboqs_name
            self.algorithm = self.policy.kem_fips_name

        self._use_lab_fallback = False
        if _HAS_LIBOQS:
            return

        enforce_pq_availability(self.policy)
        log_lab_fallback("QuantumKEM")
        self._use_lab_fallback = True
        self.algorithm = LAB_FALLBACK_ALGORITHM

    def _pq_active(self) -> bool:
        return _HAS_LIBOQS and not self._use_lab_fallback

    def generate_keypair(self, key_id: Optional[str] = None) -> KEMKeyPair:
        """Generate a KEM keypair for this node."""
        kid = key_id or f"kem-{secrets.token_hex(8)}"

        if self._pq_active():
            kem = oqs.KeyEncapsulation(self._liboqs_mechanism)
            public_key = kem.generate_keypair()
            secret_key = kem.export_secret_key()
            return KEMKeyPair(
                key_id=kid,
                public_key=public_key,
                secret_key=secret_key,
                algorithm=self.policy.kem_fips_name,
            )

        if _HAS_X25519:
            private = X25519PrivateKey.generate()
            public = private.public_key()
            return KEMKeyPair(
                key_id=kid,
                public_key=public.public_bytes_raw(),
                secret_key=private.private_bytes_raw(),
                algorithm=LAB_FALLBACK_ALGORITHM,
            )

        seed = secrets.token_bytes(64)
        pub = hashlib.sha256(seed[:32]).digest()
        return KEMKeyPair(
            key_id=kid,
            public_key=pub,
            secret_key=seed,
            algorithm=LAB_FALLBACK_ALGORITHM,
        )

    def encapsulate(self, recipient_public_key: bytes) -> EncapsulatedKey:
        """Encapsulate a shared secret for the recipient."""
        if self._pq_active():
            kem = oqs.KeyEncapsulation(self._liboqs_mechanism)
            ciphertext, shared_secret = kem.encap_secret(recipient_public_key)
            return EncapsulatedKey(
                ciphertext=ciphertext,
                shared_secret=shared_secret,
                algorithm=self.policy.kem_fips_name,
            )

        if _HAS_X25519:
            ephemeral_priv = X25519PrivateKey.generate()
            ephemeral_pub = ephemeral_priv.public_key().public_bytes_raw()
            peer_pub = X25519PublicKey.from_public_bytes(recipient_public_key)
            raw_shared = ephemeral_priv.exchange(peer_pub)
            derived = HKDF(
                algorithm=SHA256(),
                length=32,
                salt=None,
                info=b"S3M-QSS-KEM-v1",
            ).derive(raw_shared)
            return EncapsulatedKey(
                ciphertext=ephemeral_pub,
                shared_secret=derived,
                algorithm=LAB_FALLBACK_ALGORITHM,
            )

        ephemeral = secrets.token_bytes(32)
        shared = hmac.new(recipient_public_key, ephemeral, hashlib.sha512).digest()[:32]
        return EncapsulatedKey(
            ciphertext=ephemeral,
            shared_secret=shared,
            algorithm=LAB_FALLBACK_ALGORITHM,
        )

    def decapsulate(self, ciphertext: bytes, secret_key: bytes) -> bytes:
        """Decapsulate to recover the shared secret."""
        if self._pq_active():
            kem = oqs.KeyEncapsulation(self._liboqs_mechanism, secret_key=secret_key)
            return kem.decap_secret(ciphertext)

        if _HAS_X25519:
            priv = X25519PrivateKey.from_private_bytes(secret_key)
            peer_pub = X25519PublicKey.from_public_bytes(ciphertext)
            raw_shared = priv.exchange(peer_pub)
            return HKDF(
                algorithm=SHA256(),
                length=32,
                salt=None,
                info=b"S3M-QSS-KEM-v1",
            ).derive(raw_shared)

        pub = hashlib.sha256(secret_key[:32]).digest()
        return hmac.new(pub, ciphertext, hashlib.sha512).digest()[:32]
