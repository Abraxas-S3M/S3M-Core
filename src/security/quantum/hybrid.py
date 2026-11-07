"""
Hybrid key exchange combining classical ECDH and post-quantum KEM.

Defense-in-depth: both classical and PQ shared secrets are required;
neither alone is accepted for session derivation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.hashes import SHA384
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.security.quantum.kem import QuantumKEM
from src.security.quantum.policy import QuantumSecurityPolicy, load_quantum_security_policy
from src.security.quantum.signatures import QuantumSigner

_HYBRID_INFO = b"S3M-HYBRID-KX-v2"


class HybridKeyExchangeError(ValueError):
    """Hybrid handshake could not satisfy dual primitive requirements."""


@dataclass
class HybridHandshakeResult:
    """Output of a completed hybrid key exchange."""

    combined_secret: bytes
    kem_ciphertext: bytes
    classical_public: bytes
    signature: bytes
    kem_algorithm: str
    sig_algorithm: str


def _derive_hybrid_secret(
    pq_secret: Optional[bytes],
    classical_secret: Optional[bytes],
    transcript: bytes,
) -> bytes:
    """HKDF-SHA-384 over both key shares and the signed transcript."""
    if not pq_secret or not classical_secret:
        raise HybridKeyExchangeError(
            "Hybrid KDF requires both PQ and classical shared secrets; "
            "refusing classical-only or PQ-only degradation"
        )
    ikm = pq_secret + classical_secret
    return HKDF(
        algorithm=SHA384(),
        length=48,
        salt=None,
        info=_HYBRID_INFO + transcript,
    ).derive(ikm)


class HybridKeyExchange:
    """Hybrid handshake for S3M layer pairs (ML-KEM + X25519)."""

    def __init__(self, policy: Optional[QuantumSecurityPolicy] = None) -> None:
        self.policy = policy or load_quantum_security_policy()
        self.kem = QuantumKEM(policy=self.policy)
        self.signer = QuantumSigner(policy=self.policy)

    def initiate(
        self,
        initiator_sig_secret: bytes,
        responder_kem_public: bytes,
        responder_classical_public: bytes,
    ) -> HybridHandshakeResult:
        """Initiator: PQ encapsulation + ephemeral classical ECDH + sign transcript."""
        encap = self.kem.encapsulate(responder_kem_public)

        initiator_ephemeral = X25519PrivateKey.generate()
        initiator_classical_pub = initiator_ephemeral.public_key().public_bytes_raw()
        peer_classical = X25519PublicKey.from_public_bytes(responder_classical_public)
        classical_secret = initiator_ephemeral.exchange(peer_classical)

        transcript = (
            encap.ciphertext
            + initiator_classical_pub
            + responder_kem_public
            + responder_classical_public
        )
        combined = _derive_hybrid_secret(
            encap.shared_secret, classical_secret, transcript
        )

        sign_payload = transcript + combined[:16]
        signature = self.signer.sign(sign_payload, initiator_sig_secret)

        return HybridHandshakeResult(
            combined_secret=combined,
            kem_ciphertext=encap.ciphertext,
            classical_public=initiator_classical_pub,
            signature=signature,
            kem_algorithm=encap.algorithm,
            sig_algorithm=self.signer.algorithm,
        )

    def respond(
        self,
        kem_ciphertext: bytes,
        initiator_classical_public: bytes,
        responder_kem_secret: bytes,
        responder_kem_public: bytes,
        responder_classical_secret: bytes,
        initiator_sig_public: bytes,
        signature: bytes,
    ) -> bytes:
        """Responder: decapsulate PQ + classical ECDH, verify signature."""
        pq_secret = self.kem.decapsulate(kem_ciphertext, responder_kem_secret)

        responder_priv = X25519PrivateKey.from_private_bytes(responder_classical_secret)
        initiator_pub = X25519PublicKey.from_public_bytes(initiator_classical_public)
        classical_secret = responder_priv.exchange(initiator_pub)

        transcript = (
            kem_ciphertext
            + initiator_classical_public
            + responder_kem_public
            + responder_priv.public_key().public_bytes_raw()
        )
        combined = _derive_hybrid_secret(pq_secret, classical_secret, transcript)

        sign_payload = transcript + combined[:16]
        valid = self.signer.verify(sign_payload, signature, initiator_sig_public)
        if not valid:
            raise ValueError(
                "Hybrid handshake FAILED: invalid signature - "
                "possible MITM or tampered exchange"
            )
        return combined
