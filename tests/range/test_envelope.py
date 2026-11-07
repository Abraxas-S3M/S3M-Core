"""Unit tests for signed range envelopes."""

from __future__ import annotations

from range.envelope import issue_signed_test_envelope, verify_signed_test_envelope


def test_issue_and_verify_round_trip() -> None:
    envelope = issue_signed_test_envelope(
        scenario_id="scenario_a_poisoned_log",
        action_payload={"type": "http_write", "path": "/test"},
        approver_device_id="dev-1",
        approver_response="approve",
    )
    assert verify_signed_test_envelope(envelope) is True


def test_tampered_signature_fails_verification() -> None:
    envelope = issue_signed_test_envelope(
        scenario_id="scenario_c_rug_pull",
        action_payload={"tool": "cctv_status"},
        approver_device_id="dev-2",
        approver_response="deny",
    )
    tampered = envelope.to_dict()
    tampered["signature_hex"] = "00" * 64
    from range.envelope import SignedTestEnvelope

    bad = SignedTestEnvelope(**tampered)
    assert verify_signed_test_envelope(bad) is False
