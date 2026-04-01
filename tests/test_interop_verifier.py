"""Tests for Phase 16 interoperability verifier."""

from __future__ import annotations

from services.interop.verification import InteropVerifier


def test_verify_dis_conformance_roundtrip_passes():
    verifier = InteropVerifier()
    payload = verifier.verify_dis_conformance()
    assert payload["tests_failed"] == 0
    assert payload["tests_passed"] >= 4


def test_verify_c2sim_conformance_roundtrip_passes():
    verifier = InteropVerifier()
    payload = verifier.verify_c2sim_conformance()
    assert payload["tests_failed"] == 0
    assert payload["tests_passed"] >= 4


def test_verify_coordinate_accuracy_riyadh_passes():
    verifier = InteropVerifier()
    payload = verifier.verify_coordinate_accuracy()
    riyadh = next((row for row in payload["results"] if row["test"] == "Riyadh"), None)
    assert riyadh is not None
    assert riyadh["passed"] is True


def test_run_full_verification_combined_report():
    verifier = InteropVerifier()
    payload = verifier.run_full_verification()
    assert "summary" in payload
    assert "tests_passed" in payload["summary"]
    assert payload["summary"]["tests_passed"] > 0
