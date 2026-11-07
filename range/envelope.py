"""Signed test envelopes and simulated approver device responses."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ApproverResponse = Literal["approve", "deny", "duress"]

# Deterministic test authority for range rehearsals only (not for production).
_RANGE_AUTHORITY_SEED = b"s3m-range-test-authority-seed-v1-677b"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def test_authority_private_key() -> Ed25519PrivateKey:
    """Derive a stable Ed25519 key from the range test authority seed."""
    digest = hashlib.sha256(_RANGE_AUTHORITY_SEED).digest()
    return Ed25519PrivateKey.from_private_bytes(digest)


@dataclass(frozen=True, slots=True)
class SignedTestEnvelope:
    """Authority-signed action envelope used in range gate exercises."""

    envelope_id: str
    scenario_id: str
    issued_at: str
    action_digest: str
    approver_device_id: str
    approver_response: ApproverResponse
    signature_hex: str
    public_key_hex: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "scenario_id": self.scenario_id,
            "issued_at": self.issued_at,
            "action_digest": self.action_digest,
            "approver_device_id": self.approver_device_id,
            "approver_response": self.approver_response,
            "signature_hex": self.signature_hex,
            "public_key_hex": self.public_key_hex,
        }


def _canonical_payload(
    *,
    envelope_id: str,
    scenario_id: str,
    issued_at: str,
    action_digest: str,
    approver_device_id: str,
    approver_response: ApproverResponse,
) -> bytes:
    body = {
        "envelope_id": envelope_id,
        "scenario_id": scenario_id,
        "issued_at": issued_at,
        "action_digest": action_digest,
        "approver_device_id": approver_device_id,
        "approver_response": approver_response,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def issue_signed_test_envelope(
    *,
    scenario_id: str,
    action_payload: dict[str, Any],
    approver_device_id: str,
    approver_response: ApproverResponse,
    envelope_id: str | None = None,
) -> SignedTestEnvelope:
    """Build and sign a test envelope from the range authority key."""
    if not scenario_id.strip():
        raise ValueError("scenario_id is required")
    digest = hashlib.sha256(
        json.dumps(action_payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    issued_at = _utc_now().isoformat()
    env_id = envelope_id or f"env-{scenario_id}-{digest[:12]}"
    private_key = test_authority_private_key()
    public_key = private_key.public_key()
    message = _canonical_payload(
        envelope_id=env_id,
        scenario_id=scenario_id,
        issued_at=issued_at,
        action_digest=digest,
        approver_device_id=approver_device_id,
        approver_response=approver_response,
    )
    signature = private_key.sign(message)
    return SignedTestEnvelope(
        envelope_id=env_id,
        scenario_id=scenario_id,
        issued_at=issued_at,
        action_digest=digest,
        approver_device_id=approver_device_id,
        approver_response=approver_response,
        signature_hex=signature.hex(),
        public_key_hex=public_key.public_bytes_raw().hex(),
    )


def verify_signed_test_envelope(envelope: SignedTestEnvelope) -> bool:
    """Verify envelope signature with the embedded public key."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(envelope.public_key_hex))
    message = _canonical_payload(
        envelope_id=envelope.envelope_id,
        scenario_id=envelope.scenario_id,
        issued_at=envelope.issued_at,
        action_digest=envelope.action_digest,
        approver_device_id=envelope.approver_device_id,
        approver_response=envelope.approver_response,
    )
    try:
        public_key.verify(bytes.fromhex(envelope.signature_hex), message)
        return True
    except Exception:
        return False


def simulate_approver_device(response: ApproverResponse) -> dict[str, Any]:
    """Return a deterministic approver handset payload for range logging."""
    return {
        "device_attested": True,
        "response": response,
        "duress_coercion_detected": response == "duress",
        "timestamp": _utc_now().isoformat(),
    }
