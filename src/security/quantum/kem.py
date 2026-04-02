"""
Post-Quantum Key Encapsulation using NIST ML-KEM (Kyber-768).

Uses oqs-python (liboqs) when available, with a secure ECDH+HKDF
fallback for air-gapped environments where liboqs isn't yet compiled.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Tuple

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
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.hashes import SHA256

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
    """ML-KEM (Kyber-768) key encapsulation with graceful fallback.

    Priority chain:
    1. liboqs Kyber768 — full post-quantum security
    2. X25519 + HKDF — classical elliptic-curve (deployment bridge)
    3. HMAC-SHA512 ephemeral — air-gapped dev/test ONLY
    """

    KYBER_ALGORITHM = "Kyber768"
    FALLBACK_CLASSICAL = "X25519-HKDF-SHA256"
    FALLBACK_HMAC = "HMAC-SHA512-EPHEMERAL"

    def __init__(self, force_algorithm: Optional[str] = None) -> None:
        if force_algorithm:
            self.algorithm = force_algorithm
        elif _HAS_LIBOQS:
            self.algorithm = self.KYBER_ALGORITHM
        elif _HAS_X25519:
            self.algorithm = self.FALLBACK_CLASSICAL
        else:
            self.algorithm = self.FALLBACK_HMAC

    def generate_keypair(self, key_id: Optional[str] = None) -> KEMKeyPair:
        """Generate a KEM keypair for this node."""
        kid = key_id or f"kem-{secrets.token_hex(8)}"

        if self.algorithm == self.KYBER_ALGORITHM and _HAS_LIBOQS:
            kem = oqs.KeyEncapsulation(self.KYBER_ALGORITHM)
            public_key = kem.generate_keypair()
            secret_key = kem.export_secret_key()
            return KEMKeyPair(
                key_id=kid,
                public_key=public_key,
                secret_key=secret_key,
                algorithm=self.KYBER_ALGORITHM,
            )

        if self.algorithm == self.FALLBACK_CLASSICAL and _HAS_X25519:
            private = X25519PrivateKey.generate()
            public = private.public_key()
            pub_bytes = public.public_bytes_raw()
            priv_bytes = private.private_bytes_raw()
            return KEMKeyPair(
                key_id=kid,
                public_key=pub_bytes,
                secret_key=priv_bytes,
                algorithm=self.FALLBACK_CLASSICAL,
            )

        # HMAC fallback — dev/test only
        seed = secrets.token_bytes(64)
        pub = hashlib.sha256(seed[:32]).digest()
        return KEMKeyPair(
            key_id=kid,
            public_key=pub,
            secret_key=seed,
            algorithm=self.FALLBACK_HMAC,
        )

    def encapsulate(self, recipient_public_key: bytes) -> EncapsulatedKey:
        """Encapsulate a shared secret for the recipient."""
        if self.algorithm == self.KYBER_ALGORITHM and _HAS_LIBOQS:
            kem = oqs.KeyEncapsulation(self.KYBER_ALGORITHM)
            ciphertext, shared_secret = kem.encap_secret(recipient_public_key)
            return EncapsulatedKey(
                ciphertext=ciphertext,
                shared_secret=shared_secret,
                algorithm=self.KYBER_ALGORITHM,
            )

        if self.algorithm == self.FALLBACK_CLASSICAL and _HAS_X25519:
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
                algorithm=self.FALLBACK_CLASSICAL,
            )

        # HMAC fallback
        ephemeral = secrets.token_bytes(32)
        shared = hmac.new(recipient_public_key, ephemeral, hashlib.sha512).digest()[:32]
        return EncapsulatedKey(
            ciphertext=ephemeral,
            shared_secret=shared,
            algorithm=self.FALLBACK_HMAC,
        )

    def decapsulate(self, ciphertext: bytes, secret_key: bytes) -> bytes:
        """Decapsulate to recover the shared secret."""
        if self.algorithm == self.KYBER_ALGORITHM and _HAS_LIBOQS:
            kem = oqs.KeyEncapsulation(self.KYBER_ALGORITHM, secret_key=secret_key)
            return kem.decap_secret(ciphertext)

        if self.algorithm == self.FALLBACK_CLASSICAL and _HAS_X25519:
            priv = X25519PrivateKey.from_private_bytes(secret_key)
            peer_pub = X25519PublicKey.from_public_bytes(ciphertext)
            raw_shared = priv.exchange(peer_pub)
            return HKDF(
                algorithm=SHA256(),
                length=32,
                salt=None,
                info=b"S3M-QSS-KEM-v1",
            ).derive(raw_shared)

        # HMAC fallback
        pub = hashlib.sha256(secret_key[:32]).digest()
        return hmac.new(pub, ciphertext, hashlib.sha512).digest()[:32]
