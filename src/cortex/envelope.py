"""
Signed envelopes for Cortex: PQ artifact exchange and model admission authority.

Tactical context:
    Cortex ↔ S3M pipelines use quantum-policy crypto envelopes; engine manifests
    use HMAC admission signatures. Lab nodes may operate with warnings when
    admission signatures are absent.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Protocol

from src.security.quantum.kem import QuantumKEM
from src.security.quantum.policy import QuantumSecurityPolicy, load_quantum_security_policy
from src.security.quantum.signatures import QuantumSigner
from src.security.quantum.symmetric import QuantumSymmetricCipher


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def canonical_admission_bytes(fields: Mapping[str, Any]) -> bytes:
    """Deterministic JSON encoding for HMAC signing (signature field excluded)."""
    payload = {key: fields[key] for key in sorted(fields.keys()) if key != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class AdmissionSigner(Protocol):
    """Admission authority signing interface used by the model admission gate."""

    @property
    def key_id(self) -> str:
        ...

    def sign_fields(self, fields: Mapping[str, Any]) -> str:
        ...

    def verify_fields(self, fields: Mapping[str, Any], signature: str) -> bool:
        ...


@dataclass(frozen=True)
class HmacAdmissionSigner:
    """HMAC-SHA256 admission authority signer for offline edge deployments."""

    signing_key: bytes
    key_id: str = "s3m-admission-authority"

    def sign_fields(self, fields: Mapping[str, Any]) -> str:
        return hmac.new(self.signing_key, canonical_admission_bytes(fields), "sha256").hexdigest()

    def verify_fields(self, fields: Mapping[str, Any], signature: str) -> bool:
        if not signature:
            return False
        expected = self.sign_fields(fields)
        return hmac.compare_digest(expected, str(signature))


@dataclass(frozen=True)
class SignedAdmissionEnvelope:
    """Immutable signed admission record bound to one engine manifest."""

    engine_id: str
    fields: Dict[str, Any]
    signature: str
    signing_key_id: str
    signed_at: datetime

    def metadata_hash(self) -> str:
        material = self.signature + self.signing_key_id + self.signed_at.isoformat()
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @classmethod
    def seal(
        cls,
        engine_id: str,
        fields: Mapping[str, Any],
        signer: AdmissionSigner,
    ) -> "SignedAdmissionEnvelope":
        signed_at = _utcnow()
        signature = signer.sign_fields(fields)
        return cls(
            engine_id=engine_id,
            fields=dict(fields),
            signature=signature,
            signing_key_id=signer.key_id,
            signed_at=signed_at,
        )

    def verify(self, signer: AdmissionSigner) -> bool:
        if self.signing_key_id != signer.key_id:
            return False
        return signer.verify_fields(self.fields, self.signature)


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
