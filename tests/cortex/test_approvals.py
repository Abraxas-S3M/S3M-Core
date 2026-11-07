#!/usr/bin/env python3
"""Tests for out-of-band approver device service and policy gate integration."""

from __future__ import annotations

import base64
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.cortex.approvals.app import create_approvals_app
from src.cortex.approvals.crypto_util import (
    canonical_approval_payload,
    generate_device_keypair,
    new_nonce,
    sign_payload,
)
from src.cortex.approvals.service import ApprovalService
from src.cortex.approvals.store import ApprovalStore
from src.cortex.change_control_gate import ChangeControlGate


def _pub_b64(public_key: bytes) -> str:
    return base64.b64encode(public_key).decode("ascii")


def _headers(device_id: str, session_id: str | None = None) -> dict[str, str]:
    headers = {"X-Client-Cert-Fingerprint": device_id}
    if session_id:
        headers["X-Session-Id"] = session_id
    return headers


class ApprovalsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        gate = ChangeControlGate()
        store = ApprovalStore()
        self.service = ApprovalService(
            store=store,
            policy_gate=gate,
        )
        self.service.configure_escalation(["soc-watch@tactical.mil", "cmdr-alpha@tactical.mil"])
        self.service.register_admin_identity("admin-one")
        self.service.register_admin_identity("admin-two")

        self.app = create_approvals_app(self.service)
        self.client = TestClient(self.app)

        self.proposer_priv, self.proposer_pub = generate_device_keypair()
        self.approver1_priv, self.approver1_pub = generate_device_keypair()
        self.approver2_priv, self.approver2_pub = generate_device_keypair()
        self.kill1_priv, self.kill1_pub = generate_device_keypair()
        self.kill2_priv, self.kill2_pub = generate_device_keypair()

        self._register_device("proposer-device", self.proposer_pub, pin="1111")
        self._register_device("approver-one", self.approver1_pub, pin="2222")
        self._register_device("approver-two", self.approver2_pub, pin="3333")
        self._register_device("kill-holder-one", self.kill1_pub, pin="4444")
        self._register_device("kill-holder-two", self.kill2_pub, pin="5555")
        self.service.register_kill_holder("kill-holder-one")
        self.service.register_kill_holder("kill-holder-two")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _register_device(self, device_id: str, public_key: bytes, pin: str) -> None:
        started = self.service.start_device_registration(
            device_id=device_id,
            public_key_b64=_pub_b64(public_key),
            approver_label=device_id,
            duress_pin=pin,
        )
        reg_id = started["registration_id"]
        self.service.admin_approve_registration(registration_id=reg_id, admin_id="admin-one")
        self.service.admin_approve_registration(registration_id=reg_id, admin_id="admin-two")

    def _request_change(self, change_id: str, change_class: str = "D") -> dict:
        body = {
            "envelope_id": f"env-{change_id}",
            "change_class": change_class,
            "proposer_device_id": "proposer-device",
            "proposer_session_id": "session-proposer",
            "diff": "+enable elevated firewall rule on segment alpha",
            "risk_before": {"score": 0.3},
            "risk_after": {"score": 0.7},
            "blast_radius": {"nodes": ["edge-1", "edge-2"]},
            "rollback_steps": ["Revert firewall profile fw-alpha-legacy"],
            "interpreter_context": "Class D change: enable elevated firewall rule on segment alpha",
        }
        return self.service.request_change_approval(change_id, body)

    def _sign(
        self,
        *,
        private_key: bytes,
        change_id: str,
        envelope_id: str,
        decision: str,
        nonce: str | None = None,
        timestamp: str | None = None,
    ) -> dict:
        nonce = nonce or new_nonce()
        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        payload = canonical_approval_payload(
            change_id=change_id,
            envelope_id=envelope_id,
            decision=decision,
            timestamp=timestamp,
            nonce=nonce,
        )
        return {
            "envelope_id": envelope_id,
            "decision": decision,
            "timestamp": timestamp,
            "nonce": nonce,
            "signature_b64": sign_payload(private_key, payload),
        }

    def test_replayed_approval_is_rejected(self) -> None:
        change_id = "chg-replay"
        req = self._request_change(change_id)
        body = self._sign(
            private_key=self.approver1_priv,
            change_id=change_id,
            envelope_id=req["envelope_id"],
            decision="APPROVE",
        )
        first = self.service.submit_approval(
            change_id,
            device_id="approver-one",
            session_id=None,
            duress_pin=None,
            **body,
        )
        self.assertEqual(first["recorded_decision"], "APPROVE")
        with self.assertRaises(ValueError):
            self.service.submit_approval(
                change_id,
                device_id="approver-one",
                session_id=None,
                duress_pin=None,
                **body,
            )

    def test_proposer_self_approval_is_rejected(self) -> None:
        change_id = "chg-self"
        req = self._request_change(change_id, change_class="C")
        body = self._sign(
            private_key=self.proposer_priv,
            change_id=change_id,
            envelope_id=req["envelope_id"],
            decision="APPROVE",
        )
        with self.assertRaises(PermissionError):
            self.service.submit_approval(
                change_id,
                device_id="proposer-device",
                session_id=None,
                duress_pin=None,
                **body,
            )

        body2 = self._sign(
            private_key=self.approver1_priv,
            change_id=change_id,
            envelope_id=req["envelope_id"],
            decision="APPROVE",
        )
        with self.assertRaises(PermissionError):
            self.service.submit_approval(
                change_id,
                device_id="approver-one",
                session_id="session-proposer",
                duress_pin=None,
                **body2,
            )

    def test_duress_records_deny_and_raises_alert(self) -> None:
        change_id = "chg-duress"
        req = self._request_change(change_id, change_class="C")
        body = self._sign(
            private_key=self.approver1_priv,
            change_id=change_id,
            envelope_id=req["envelope_id"],
            decision="APPROVE",
        )
        result = self.service.submit_approval(
            change_id,
            device_id="approver-one",
            session_id=None,
            duress_pin="2222",
            **body,
        )
        self.assertEqual(result["ui_decision"], "APPROVE")
        self.assertEqual(result["recorded_decision"], "DENY")
        self.assertTrue(result["alert_raised"])
        self.assertTrue(result["blocked"])
        self.assertGreaterEqual(len(self.service.store.critical_alerts), 1)

        body2 = self._sign(
            private_key=self.approver1_priv,
            change_id=change_id,
            envelope_id=req["envelope_id"],
            decision="APPROVE",
        )
        with self.assertRaises(PermissionError):
            self.service.submit_approval(
                change_id,
                device_id="approver-one",
                session_id=None,
                duress_pin=None,
                **body2,
            )

    def test_two_distinct_approvers_satisfy_class_d(self) -> None:
        change_id = "chg-class-d"
        req = self._request_change(change_id, change_class="D")
        self.assertEqual(req["required_approval_count"], 2)
        for device_id, priv in (
            ("approver-one", self.approver1_priv),
            ("approver-two", self.approver2_priv),
        ):
            body = self._sign(
                private_key=priv,
                change_id=change_id,
                envelope_id=req["envelope_id"],
                decision="APPROVE",
            )
            self.service.submit_approval(
                change_id,
                device_id=device_id,
                session_id=None,
                duress_pin=None,
                **body,
            )
        self.assertTrue(self.service.gate_satisfied(change_id))

    def test_kill_switch_blocks_writes_and_needs_two_to_disengage(self) -> None:
        change_id = "chg-kill"
        self.service.engage_kill("kill-holder-one")
        self.assertTrue(self.service.policy_gate.kill_engaged)
        with self.assertRaises(RuntimeError):
            self._request_change(change_id)

        first = self.service.disengage_kill("kill-holder-one")
        self.assertTrue(first["kill_engaged"])
        self.assertEqual(first["votes"], 1)

        second = self.service.disengage_kill("kill-holder-two")
        self.assertFalse(second["kill_engaged"])
        self._request_change(change_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
