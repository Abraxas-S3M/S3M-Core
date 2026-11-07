"""
Signed encrypted envelopes for Cortex ↔ S3M artifact exchange.

Uses the same quantum security policy loader as the QSS ring so tactical
cyber analysis pipelines cannot silently weaken crypto relative to core S3M.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.security.quantum.kem import QuantumKEM
from src.security.quantum.policy import QuantumSecurityPolicy, load_quantum_security_policy
from src.security.quantum.signatures import QuantumSigner
from src.security.quantum.symmetric import QuantumSymmetricCipher


@dataclass
class CortexEnvelope:
    """Cortex-bound payload with PQ-protected session key and signature."""

    payload_b64: str
    kem_ciphertext_hex: str
    kem_algorithm: str
    signature_hex: str
    sig_algorithm: str
    layer_tag: str = "cortex-bridge"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload_b64": self.payload_b64,
            "kem_ciphertext_hex": self.kem_ciphertext_hex,
            "kem_algorithm": self.kem_algorithm,
            "signature_hex": self.signature_hex,
            "sig_algorithm": self.sig_algorithm,
            "layer_tag": self.layer_tag,
        }


class CortexEnvelopeCodec:
    """Seal and open Cortex messages under the shared quantum policy."""

    def __init__(self, policy: Optional[QuantumSecurityPolicy] = None) -> None:
        self.policy = policy or load_quantum_security_policy()
        self.kem = QuantumKEM(policy=self.policy)
        self.signer = QuantumSigner(policy=self.policy)
        self.cipher = QuantumSymmetricCipher()

    def seal(
        self,
        plaintext: bytes,
        recipient_kem_public: bytes,
        signer_secret: bytes,
    ) -> CortexEnvelope:
        encap = self.kem.encapsulate(recipient_kem_public)
        session_key = self.cipher.derive_session_key(
            encap.shared_secret, context=b"S3M-CORTEX-ENVELOPE-v1"
        )
        sealed = self.cipher.encrypt(plaintext, session_key, layer_tag="cortex-bridge")
        sig_material = json.dumps(
            {
                "ct": encap.ciphertext.hex(),
                "nonce": sealed.nonce.hex(),
                "ciphertext": sealed.ciphertext.hex(),
            },
            sort_keys=True,
        ).encode("utf-8")
        signature = self.signer.sign(sig_material, signer_secret)
        import base64

        return CortexEnvelope(
            payload_b64=base64.b64encode(sealed.ciphertext).decode("ascii"),
            kem_ciphertext_hex=encap.ciphertext.hex(),
            kem_algorithm=encap.algorithm,
            signature_hex=signature.hex(),
            sig_algorithm=self.signer.algorithm,
        )

    def policy_summary(self) -> Dict[str, Any]:
        """Expose active crypto posture for Cortex health checks."""
        return {
            "crypto_mode": self.policy.crypto_mode.value,
            "kem_algorithm": self.policy.kem_fips_name,
            "sig_algorithm": self.policy.sig_fips_name,
            "hybrid_mode": self.policy.hybrid_mode,
            "cnsa_profile": self.policy.cnsa_profile,
        }
