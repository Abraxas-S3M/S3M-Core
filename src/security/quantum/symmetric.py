"""
Authenticated symmetric encryption for S3M inter-layer data protection.
Uses AES-256-GCM (AEAD) with quantum-derived session keys.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Tuple

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_AESGCM = True
except ImportError:
    _HAS_AESGCM = False


@dataclass
class SealedPayload:
    """Triple-layer encrypted payload container."""
    nonce: bytes
    ciphertext: bytes
    aad: bytes
    layer_tag: str
    sequence: int


class QuantumSymmetricCipher:
    """AES-256-GCM with quantum-derived key material.

    The session key is derived from the KEM shared secret via HKDF.
    All payloads include authenticated associated data for tamper evidence.
    """

    NONCE_SIZE = 12
    KEY_SIZE = 32
    TAG_SIZE = 16

    def __init__(self) -> None:
        self._sequence_counter = 0

    def derive_session_key(
        self, shared_secret: bytes, context: bytes = b"S3M-QSS-SESSION-v1",
    ) -> bytes:
        """Derive a 256-bit session key from KEM shared secret."""
        try:
            from cryptography.hazmat.primitives.kdf.hkdf import HKDF
            from cryptography.hazmat.primitives.hashes import SHA256
            return HKDF(
                algorithm=SHA256(), length=self.KEY_SIZE,
                salt=None, info=context,
            ).derive(shared_secret)
        except ImportError:
            return hashlib.sha256(shared_secret + context).digest()

    def encrypt(
        self, plaintext: bytes, session_key: bytes,
        layer_tag: str = "unknown", aad: bytes = b"",
    ) -> SealedPayload:
        """Encrypt with AES-256-GCM and return a SealedPayload."""
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        self._sequence_counter += 1

        full_aad = (
            layer_tag.encode("utf-8") + b"|"
            + str(self._sequence_counter).encode("utf-8") + b"|" + aad
        )

        if _HAS_AESGCM:
            aesgcm = AESGCM(session_key)
            ciphertext = aesgcm.encrypt(nonce, plaintext, full_aad)
        else:
            ciphertext = self._encrypt_fallback(plaintext, session_key, nonce, full_aad)

        return SealedPayload(
            nonce=nonce, ciphertext=ciphertext, aad=full_aad,
            layer_tag=layer_tag, sequence=self._sequence_counter,
        )

    def decrypt(self, payload: SealedPayload, session_key: bytes) -> bytes:
        """Decrypt and authenticate a SealedPayload."""
        if _HAS_AESGCM:
            aesgcm = AESGCM(session_key)
            return aesgcm.decrypt(payload.nonce, payload.ciphertext, payload.aad)
        return self._decrypt_fallback(
            payload.ciphertext, session_key, payload.nonce, payload.aad
        )

    def _keystream(self, key: bytes, nonce: bytes, length: int) -> bytes:
        stream = bytearray()
        ctr = 0
        while len(stream) < length:
            block = hashlib.sha256(key + nonce + ctr.to_bytes(8, "big")).digest()
            stream.extend(block)
            ctr += 1
        return bytes(stream[:length])

    def _encrypt_fallback(
        self, plaintext: bytes, key: bytes, nonce: bytes, aad: bytes,
    ) -> bytes:
        stream = self._keystream(key, nonce, len(plaintext))
        ct = bytes(a ^ b for a, b in zip(plaintext, stream))
        tag = hmac.new(key, nonce + aad + ct, hashlib.sha256).digest()[:self.TAG_SIZE]
        return ct + tag

    def _decrypt_fallback(
        self, ciphertext: bytes, key: bytes, nonce: bytes, aad: bytes,
    ) -> bytes:
        ct, tag = ciphertext[:-self.TAG_SIZE], ciphertext[-self.TAG_SIZE:]
        expected = hmac.new(key, nonce + aad + ct, hashlib.sha256).digest()[:self.TAG_SIZE]
        if not hmac.compare_digest(tag, expected):
            raise ValueError("GCM fallback: integrity check failed — tampered payload")
        stream = self._keystream(key, nonce, len(ct))
        return bytes(a ^ b for a, b in zip(ct, stream))
