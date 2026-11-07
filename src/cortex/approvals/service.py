"""Business logic for out-of-band approver devices and policy gate integration."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from src.cortex.approvals.audit import ApprovalsAudit
from src.cortex.approvals.crypto_util import (
    canonical_approval_payload,
    hash_duress_pin,
    new_nonce,
    new_salt,
    verify_payload,
)
from src.cortex.approvals.payload_builder import ChangePayloadBuilder
from src.cortex.approvals.soc_bridge import ApprovalsSOCBridge
from src.cortex.approvals.store import ApprovalStore, PendingChange, PendingRegistration, RegisteredDevice
from src.cortex.change_control_gate import (
    ChangeClass,
    ChangeControlGate,
    ChangeEnvelope,
    SignedDeviceApproval,
)

FRESHNESS_WINDOW_SECONDS = 180


class ApprovalService:
    def __init__(
        self,
        *,
        store: Optional[ApprovalStore] = None,
        policy_gate: Optional[ChangeControlGate] = None,
        audit: Optional[ApprovalsAudit] = None,
        soc: Optional[ApprovalsSOCBridge] = None,
    ) -> None:
        self.store = store or ApprovalStore()
        self.policy_gate = policy_gate or ChangeControlGate()
        self.audit = audit or ApprovalsAudit()
        self.payload_builder = ChangePayloadBuilder()
        self.soc = soc or ApprovalsSOCBridge()

    def configure_escalation(self, recipients: List[str]) -> None:
        self.store.set_escalation_list(recipients)
        self.soc.escalation_list = list(recipients)

    def register_admin_identity(self, admin_id: str) -> None:
        self.store.register_admin(admin_id)
        self.audit.record("admin_identity_registered", {"admin_id": admin_id})

    def register_kill_holder(self, device_id: str) -> None:
        self.store.kill_holders.add(device_id)
        self.policy_gate.register_kill_holder(device_id)
        self.audit.record("kill_holder_registered", {"device_id": device_id})

    def start_device_registration(
        self,
        *,
        device_id: str,
        public_key_b64: str,
        approver_label: str,
        duress_pin: str,
    ) -> Dict[str, Any]:
        salt = new_salt()
        pending = PendingRegistration(
            registration_id=str(uuid.uuid4()),
            device_id=device_id,
            public_key_b64=public_key_b64,
            approver_label=approver_label,
            duress_salt=salt,
            duress_hash=hash_duress_pin(duress_pin, salt),
        )
        with self.store._lock:
            self.store.pending_registrations[pending.registration_id] = pending
        self.audit.record(
            "device_registration_started",
            {"device_id": device_id, "registration_id": pending.registration_id},
        )
        return {"registration_id": pending.registration_id, "status": "pending_admin_two_person"}

    def admin_approve_registration(self, *, registration_id: str, admin_id: str) -> Dict[str, Any]:
        with self.store._lock:
            pending = self.store.pending_registrations.get(registration_id)
            if pending is None:
                raise KeyError("registration not found")
            if admin_id not in self.store.admin_identities:
                raise PermissionError("unknown admin identity")
            if admin_id in pending.admin_votes:
                raise PermissionError("admin already voted on this registration")
            pending.admin_votes.add(admin_id)
            votes = len(pending.admin_votes)
            if votes < 2:
                self.audit.record(
                    "device_registration_admin_vote",
                    {"registration_id": registration_id, "admin_id": admin_id, "votes": votes},
                )
                return {"status": "pending", "votes": votes, "required": 2}
            device = RegisteredDevice(
                device_id=pending.device_id,
                public_key_b64=pending.public_key_b64,
                approver_label=pending.approver_label,
                duress_salt=pending.duress_salt,
                duress_hash=pending.duress_hash,
                registered_at=self.store.now_ts(),
            )
            self.store.devices[pending.device_id] = device
            del self.store.pending_registrations[registration_id]
        self.audit.record(
            "device_registration_complete",
            {"device_id": device.device_id, "approver_label": device.approver_label},
            severity="INFO",
        )
        return {"status": "registered", "device_id": device.device_id}

    def _required_count(self, change_class: str) -> int:
        if change_class == ChangeClass.D.value:
            return 2
        if change_class == ChangeClass.C.value:
            return 1
        return 0

    def request_change_approval(self, change_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        self.policy_gate.assert_writes_allowed()
        change_class = str(body["change_class"]).upper()
        required = self._required_count(change_class)
        device_payload = self.payload_builder.build(
            change_id=change_id,
            envelope_id=body["envelope_id"],
            diff=body["diff"],
            interpreter_context=body.get("interpreter_context", ""),
            risk_before=body.get("risk_before", {}),
            risk_after=body.get("risk_after", {}),
            blast_radius=body.get("blast_radius", {}),
            rollback_steps=body.get("rollback_steps", []),
        )
        change = PendingChange(
            change_id=change_id,
            envelope_id=body["envelope_id"],
            change_class=change_class,
            required_approval_count=required,
            proposer_device_id=body["proposer_device_id"],
            proposer_session_id=body["proposer_session_id"],
            diff=body["diff"],
            risk_before=body.get("risk_before", {}),
            risk_after=body.get("risk_after", {}),
            blast_radius=body.get("blast_radius", {}),
            rollback_steps=body.get("rollback_steps", []),
            interpreter_context=body.get("interpreter_context", ""),
            device_payload=device_payload,
        )
        notified = self._select_approver_devices(exclude={body["proposer_device_id"]})
        change.notified_devices = notified
        with self.store._lock:
            self.store.changes[change_id] = change
        self.audit.record(
            "change_approval_requested",
            {
                "change_id": change_id,
                "envelope_id": change.envelope_id,
                "change_class": change_class,
                "notified_devices": notified,
            },
        )
        return {
            "change_id": change_id,
            "envelope_id": change.envelope_id,
            "notified_devices": notified,
            "required_approval_count": required,
            "device_payload": device_payload,
        }

    def _select_approver_devices(self, *, exclude: Set[str]) -> List[str]:
        with self.store._lock:
            ids = [
                device_id
                for device_id, device in self.store.devices.items()
                if device_id not in exclude and not device.blocked
            ]
        return ids[: max(4, len(ids))]

    def get_device_payload(self, change_id: str, device_id: str) -> Dict[str, Any]:
        with self.store._lock:
            change = self.store.changes.get(change_id)
            device = self.store.devices.get(device_id)
        if change is None:
            raise KeyError("change not found")
        if device is None:
            raise PermissionError("device not registered")
        if device_id not in change.notified_devices:
            raise PermissionError("device not assigned to this change")
        return dict(change.device_payload)

    def _parse_ts(self, timestamp: str) -> datetime:
        normalized = timestamp.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)

    def _fresh(self, timestamp: str) -> bool:
        try:
            ts = self._parse_ts(timestamp)
        except ValueError:
            return False
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = abs((now - ts).total_seconds())
        return delta <= FRESHNESS_WINDOW_SECONDS

    def _nonce_used(self, nonce: str) -> bool:
        with self.store._lock:
            return nonce in self.store.used_nonces

    def _mark_nonce(self, nonce: str) -> None:
        with self.store._lock:
            self.store.used_nonces[nonce] = datetime.now(timezone.utc).timestamp()

    def submit_approval(
        self,
        change_id: str,
        *,
        device_id: str,
        session_id: Optional[str],
        envelope_id: str,
        decision: str,
        timestamp: str,
        nonce: str,
        signature_b64: str,
        duress_pin: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.policy_gate.assert_writes_allowed()
        with self.store._lock:
            change = self.store.changes.get(change_id)
            device = self.store.devices.get(device_id)
        if change is None:
            raise KeyError("change not found")
        if device is None:
            raise PermissionError("device not registered")
        if device.blocked:
            raise PermissionError("approver device blocked")
        if envelope_id != change.envelope_id:
            raise ValueError("envelope mismatch")
        if device_id == change.proposer_device_id:
            raise PermissionError("proposer cannot self-approve")
        if session_id and session_id == change.proposer_session_id:
            raise PermissionError("proposer session cannot approve its own change")
        if self._nonce_used(nonce):
            raise ValueError("replay detected")
        if not self._fresh(timestamp):
            raise ValueError("stale approval timestamp")

        payload = canonical_approval_payload(
            change_id=change_id,
            envelope_id=envelope_id,
            decision=decision,
            timestamp=timestamp,
            nonce=nonce,
        )
        public_key = base64.b64decode(device.public_key_b64.encode("ascii"))
        if not verify_payload(public_key, payload, signature_b64):
            raise ValueError("invalid signature")

        self._mark_nonce(nonce)

        ui_decision = decision.upper()
        recorded = decision.upper()
        alert_raised = False
        blocked = False

        if duress_pin and hash_duress_pin(duress_pin, device.duress_salt) == device.duress_hash:
            ui_decision = "APPROVE"
            recorded = "DENY"
            alert = self.soc.raise_duress_alert(
                device_id=device_id,
                change_id=change_id,
                envelope_id=envelope_id,
            )
            with self.store._lock:
                device.blocked = True
                self.store.critical_alerts.append(alert)
            alert_raised = True
            blocked = True
            self.audit.record(
                "duress_pin_triggered",
                alert,
                severity="CRITICAL",
            )

        approval_record = {
            "device_id": device_id,
            "decision": recorded,
            "ui_decision": ui_decision,
            "timestamp": timestamp,
            "nonce": nonce,
            "signature_b64": signature_b64,
            "duress": alert_raised,
        }
        with self.store._lock:
            change.approvals.append(approval_record)

        gate_approval = SignedDeviceApproval(
            change_id=change_id,
            envelope_id=envelope_id,
            decision=ui_decision if not alert_raised else "APPROVE",
            effective_decision=recorded,
            approver_device_id=device_id,
            channel="out_of_band_device",
            timestamp=timestamp,
            nonce=nonce,
            signature_b64=signature_b64,
        )
        self.policy_gate.record_approval(gate_approval)
        self.audit.record(
            "approval_submitted",
            {
                "change_id": change_id,
                "device_id": device_id,
                "recorded_decision": recorded,
                "ui_decision": ui_decision,
                "duress": alert_raised,
            },
            severity="WARNING" if alert_raised else "INFO",
        )
        return {
            "ui_decision": ui_decision,
            "recorded_decision": recorded,
            "alert_raised": alert_raised,
            "blocked": blocked,
        }

    def build_envelope(self, change_id: str) -> ChangeEnvelope:
        with self.store._lock:
            change = self.store.changes[change_id]
        return ChangeEnvelope(
            envelope_id=change.envelope_id,
            change_id=change.change_id,
            change_class=ChangeClass(change.change_class),
            required_approval_count=change.required_approval_count,
            proposer_device_id=change.proposer_device_id,
            proposer_session_id=change.proposer_session_id,
            diff=change.diff,
            risk_before=change.risk_before,
            risk_after=change.risk_after,
            blast_radius=change.blast_radius,
            rollback_steps=change.rollback_steps,
        )

    def gate_satisfied(self, change_id: str) -> bool:
        envelope = self.build_envelope(change_id)
        return self.policy_gate.envelope_satisfied(envelope)

    def engage_kill(self, holder_device_id: str) -> Dict[str, Any]:
        if holder_device_id not in self.store.kill_holders:
            raise PermissionError("not a kill holder")
        result = self.policy_gate.kill(holder_device_id)
        self.audit.record("kill_switch_engaged", result, severity="CRITICAL")
        return result

    def disengage_kill(self, holder_device_id: str) -> Dict[str, Any]:
        if holder_device_id not in self.store.kill_holders:
            raise PermissionError("not a kill holder")
        result = self.policy_gate.disengage_kill(holder_device_id)
        self.audit.record("kill_switch_disengage_vote", result, severity="WARNING")
        return result
