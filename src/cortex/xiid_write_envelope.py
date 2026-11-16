"""Approval envelope required before broker forwards mutating XiiD actions.

Military/tactical context:
An operator approval must authorize *this* change, not "any change of this kind for the
rest of the session". Envelopes can therefore bind the exact tool arguments (by digest)
and carry an expiry. Unbound envelopes remain verifiable for backward compatibility, but
brokers configured with ``require_bound_envelopes=True`` refuse them.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def arguments_digest(arguments: Mapping[str, Any] | None) -> str:
    """Canonical SHA-256 over tool arguments (sorted keys, no whitespace)."""
    canonical = json.dumps(dict(arguments or {}), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(slots=True, frozen=True)
class WriteEnvelope:
    """Operator-signed approval binding one tactical write to a session."""

    approval_id: str
    operator_id: str
    session_id: str
    action: str
    issued_at: str
    signature: str
    args_digest: str = ""
    expires_at: str = ""

    @property
    def is_bound(self) -> bool:
        return bool(self.args_digest)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "operator_id": self.operator_id,
            "session_id": self.session_id,
            "action": self.action,
            "issued_at": self.issued_at,
            "signature": self.signature,
            "args_digest": self.args_digest,
            "expires_at": self.expires_at,
        }

    @staticmethod
    def _material(
        approval_id: str,
        operator_id: str,
        session_id: str,
        action: str,
        issued_at: str,
        args_digest: str,
        expires_at: str,
    ) -> bytes:
        base = f"{approval_id}|{operator_id}|{session_id}|{action}|{issued_at}"
        # Legacy (unbound) envelopes keep the original signing material unchanged.
        if args_digest or expires_at:
            base += f"|{args_digest}|{expires_at}"
        return base.encode("utf-8")

    @classmethod
    def issue(
        cls,
        *,
        operator_id: str,
        session_id: str,
        action: str,
        signing_key: bytes,
        arguments: Optional[Mapping[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
    ) -> "WriteEnvelope":
        approval_id = secrets.token_hex(8)
        now = datetime.now(timezone.utc)
        issued_at = now.isoformat()
        args_digest = arguments_digest(arguments) if arguments is not None else ""
        expires_at = (now + timedelta(seconds=int(ttl_seconds))).isoformat() if ttl_seconds else ""
        material = cls._material(approval_id, operator_id, session_id, action, issued_at, args_digest, expires_at)
        signature = hmac.new(signing_key, material, hashlib.sha256).hexdigest()
        return cls(
            approval_id=approval_id,
            operator_id=operator_id,
            session_id=session_id,
            action=action,
            issued_at=issued_at,
            signature=signature,
            args_digest=args_digest,
            expires_at=expires_at,
        )

    def verify(self, signing_key: bytes) -> bool:
        material = self._material(
            self.approval_id,
            self.operator_id,
            self.session_id,
            self.action,
            self.issued_at,
            self.args_digest,
            self.expires_at,
        )
        expected = hmac.new(signing_key, material, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.signature)

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        if not self.expires_at:
            return False
        current = now or datetime.now(timezone.utc)
        return current >= datetime.fromisoformat(self.expires_at)

    def covers_arguments(self, arguments: Mapping[str, Any] | None) -> bool:
        if not self.args_digest:
            return True
        return hmac.compare_digest(self.args_digest, arguments_digest(arguments))
