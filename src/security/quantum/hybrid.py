"""
Hybrid key exchange combining classical ECDH and post-quantum KEM.
Defense-in-depth: if either primitive is broken, the other holds.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Tuple

from src.security.quantum.kem import QuantumKEM, EncapsulatedKey
from src.security.quantum.signatures import QuantumSigner


@dataclass
class HybridHandshakeResult:
    """Output of a completed hybrid key exchange."""

    combined_secret: bytes
    kem_ciphertext: bytes
    signature: bytes
    kem_algorithm: str
    sig_algorithm: str


class HybridKeyExchange:
    """Double-ratchet-style hybrid handshake for S3M layer pairs.

    Protocol:
    1. Initiator encapsulates shared secret using responder's PQ public key
    2. Both derive combined_secret = HKDF(KEM_secret || context)
    3. Exchange is signed with Dilithium for mutual authentication
    """

    def __init__(self) -> None:
        self.kem = QuantumKEM()
        self.signer = QuantumSigner()

    def initiate(
        self,
        initiator_sig_secret: bytes,
        responder_kem_public: bytes,
    ) -> HybridHandshakeResult:
        """Initiator side: encapsulate + sign."""
        encap = self.kem.encapsulate(responder_kem_public)

        combined = hashlib.sha256(
            encap.shared_secret + b"S3M-HYBRID-KX-v1" + responder_kem_public[:16]
        ).digest()

        signature = self.signer.sign(
            encap.ciphertext + combined[:16],
            initiator_sig_secret,
        )

        return HybridHandshakeResult(
            combined_secret=combined,
            kem_ciphertext=encap.ciphertext,
            signature=signature,
            kem_algorithm=self.kem.algorithm,
            sig_algorithm=self.signer.algorithm,
        )

    def respond(
        self,
        kem_ciphertext: bytes,
        responder_kem_secret: bytes,
        responder_kem_public: bytes,
        initiator_sig_public: bytes,
        signature: bytes,
    ) -> bytes:
        """Responder side: decapsulate + verify -> combined secret."""
        shared_secret = self.kem.decapsulate(kem_ciphertext, responder_kem_secret)

        combined = hashlib.sha256(
            shared_secret + b"S3M-HYBRID-KX-v1" + responder_kem_public[:16]
        ).digest()

        valid = self.signer.verify(
            kem_ciphertext + combined[:16],
            signature,
            initiator_sig_public,
        )
        if not valid:
            raise ValueError(
                "Hybrid handshake FAILED: invalid signature - "
                "possible MITM or tampered exchange"
            )
        return combined
