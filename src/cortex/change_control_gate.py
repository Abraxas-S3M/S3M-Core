"""Class C/D change control with signed out-of-band device approvals and kill switch.

Military/tactical context: configuration mutations at class C/D require device-bound
signatures that resist console deepfakes; kill switch halts writes under coercion.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class ChangeClass(str, Enum):
    """Change severity tier; C/D mandate out-of-band device approval."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"


@dataclass(frozen=True)
class SignedDeviceApproval:
    """One cryptographically signed human decision bound to a change envelope."""

    change_id: str
    envelope_id: str
    decision: str
    approver_device_id: str
    channel: str
    timestamp: str
    nonce: str
    signature_b64: str
    effective_decision: Optional[str] = None

    def is_out_of_band_device(self) -> bool:
        return self.channel == "out_of_band_device"


@dataclass
class ChangeEnvelope:
    """Immutable approval contract for a pending configuration mutation."""

    envelope_id: str
    change_id: str
    change_class: ChangeClass
    required_approval_count: int
    proposer_device_id: str
    proposer_session_id: str
    diff: str
    risk_before: Dict[str, Any]
    risk_after: Dict[str, Any]
    blast_radius: Dict[str, Any]
    rollback_steps: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class ChangeControlGate:
    """Central write gate for class C/D changes; kill switch blocks mutating operations."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._kill_engaged = False
        self._pending_disengage_votes: Set[str] = set()
        self._approvals_by_envelope: Dict[str, List[SignedDeviceApproval]] = {}
        self._registered_kill_holders: Set[str] = set()

    @property
    def kill_engaged(self) -> bool:
        with self._lock:
            return self._kill_engaged

    def register_kill_holder(self, holder_id: str) -> None:
        """Authorize a device identity to operate the tactical kill switch."""
        with self._lock:
            self._registered_kill_holders.add(holder_id)

    def kill(self, holder_id: str) -> Dict[str, Any]:
        """Engage kill switch (one registered holder)."""
        with self._lock:
            if holder_id not in self._registered_kill_holders:
                raise PermissionError("holder not registered for kill switch")
            self._kill_engaged = True
            self._pending_disengage_votes.clear()
            return {"kill_engaged": True, "holder_id": holder_id}

    def disengage_kill(self, holder_id: str) -> Dict[str, Any]:
        """Disengage requires two distinct registered holders."""
        with self._lock:
            if holder_id not in self._registered_kill_holders:
                raise PermissionError("holder not registered for kill switch")
            if not self._kill_engaged:
                return {"kill_engaged": False, "votes": 0, "required": 2}
            self._pending_disengage_votes.add(holder_id)
            votes = len(self._pending_disengage_votes)
            if votes >= 2:
                self._kill_engaged = False
                self._pending_disengage_votes.clear()
                return {"kill_engaged": False, "disengaged": True, "votes": votes}
            return {"kill_engaged": True, "disengaged": False, "votes": votes, "required": 2}

    def assert_writes_allowed(self) -> None:
        """Raise when kill switch blocks tactical writes."""
        with self._lock:
            if self._kill_engaged:
                raise RuntimeError("policy_gate_kill_engaged")

    def record_approval(self, approval: SignedDeviceApproval) -> None:
        """Persist gate-facing approval after out-of-band service verification."""
        if not approval.is_out_of_band_device():
            raise ValueError("only out_of_band_device channel accepted")
        with self._lock:
            bucket = self._approvals_by_envelope.setdefault(approval.envelope_id, [])
            bucket.append(approval)

    def satisfied_approvals(
        self,
        envelope: ChangeEnvelope,
        *,
        exclude_device_ids: Optional[Set[str]] = None,
    ) -> List[SignedDeviceApproval]:
        """Return distinct APPROVE decisions usable for this envelope."""
        exclude = exclude_device_ids or set()
        exclude.add(envelope.proposer_device_id)
        with self._lock:
            raw = list(self._approvals_by_envelope.get(envelope.envelope_id, []))
        usable: List[SignedDeviceApproval] = []
        seen: Set[str] = set()
        for item in raw:
            effective = (item.effective_decision or item.decision).upper()
            if effective != "APPROVE":
                continue
            if item.approver_device_id in exclude:
                continue
            if item.approver_device_id in seen:
                continue
            seen.add(item.approver_device_id)
            usable.append(item)
        return usable

    def envelope_satisfied(self, envelope: ChangeEnvelope) -> bool:
        """True when enough distinct non-proposer approvers have approved."""
        count = len(
            self.satisfied_approvals(
                envelope,
                exclude_device_ids={envelope.proposer_device_id},
            )
        )
        return count >= envelope.required_approval_count
