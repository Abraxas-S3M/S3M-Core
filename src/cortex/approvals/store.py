"""In-memory tactical store for approver devices and pending changes."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set


@dataclass
class RegisteredDevice:
    device_id: str
    public_key_b64: str
    approver_label: str
    duress_salt: str
    duress_hash: str
    registered_at: str
    blocked: bool = False


@dataclass
class PendingRegistration:
    registration_id: str
    device_id: str
    public_key_b64: str
    approver_label: str
    duress_salt: str
    duress_hash: str
    admin_votes: Set[str] = field(default_factory=set)


@dataclass
class PendingChange:
    change_id: str
    envelope_id: str
    change_class: str
    required_approval_count: int
    proposer_device_id: str
    proposer_session_id: str
    diff: str
    risk_before: Dict[str, Any]
    risk_after: Dict[str, Any]
    blast_radius: Dict[str, Any]
    rollback_steps: List[str]
    interpreter_context: str
    device_payload: Dict[str, Any]
    notified_devices: List[str] = field(default_factory=list)
    approvals: List[Dict[str, Any]] = field(default_factory=list)


class ApprovalStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.devices: Dict[str, RegisteredDevice] = {}
        self.pending_registrations: Dict[str, PendingRegistration] = {}
        self.changes: Dict[str, PendingChange] = {}
        self.used_nonces: Dict[str, float] = {}
        self.admin_identities: Set[str] = set()
        self.kill_holders: Set[str] = set()
        self.critical_alerts: List[Dict[str, Any]] = []
        self.escalation_list: List[str] = []

    def set_escalation_list(self, recipients: List[str]) -> None:
        with self._lock:
            self.escalation_list = list(recipients)

    def register_admin(self, admin_id: str) -> None:
        with self._lock:
            self.admin_identities.add(admin_id)

    def now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat()
