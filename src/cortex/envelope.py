"""Signed admission envelopes for Cortex model manifests.

Tactical context:
    Only manifests countersigned by the admission authority may load in production.
    Lab nodes may operate with warnings when signatures are absent.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Protocol


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
