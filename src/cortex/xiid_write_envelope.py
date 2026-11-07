"""Approval envelope required before broker forwards mutating XiiD actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import secrets
from typing import Any, Dict


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True, frozen=True)
class WriteEnvelope:
    """Operator-signed approval binding one tactical write to a session."""

    approval_id: str
    operator_id: str
    session_id: str
    action: str
    issued_at: str
    signature: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "operator_id": self.operator_id,
            "session_id": self.session_id,
            "action": self.action,
            "issued_at": self.issued_at,
            "signature": self.signature,
        }

    @classmethod
    def issue(
        cls,
        *,
        operator_id: str,
        session_id: str,
        action: str,
        signing_key: bytes,
    ) -> "WriteEnvelope":
        approval_id = secrets.token_hex(8)
        issued_at = _utc_now_iso()
        material = f"{approval_id}|{operator_id}|{session_id}|{action}|{issued_at}".encode("utf-8")
        signature = hmac.new(signing_key, material, hashlib.sha256).hexdigest()
        return cls(
            approval_id=approval_id,
            operator_id=operator_id,
            session_id=session_id,
            action=action,
            issued_at=issued_at,
            signature=signature,
        )

    def verify(self, signing_key: bytes) -> bool:
        material = (
            f"{self.approval_id}|{self.operator_id}|{self.session_id}|{self.action}|{self.issued_at}"
        ).encode("utf-8")
        expected = hmac.new(signing_key, material, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature)
