"""
Tests that Phase 10 security components work across the full stack.
"""

from __future__ import annotations

import pytest

from tests.integration._availability import has_module


SECURITY_AVAILABLE = has_module("src.security")


@pytest.mark.skipif(not SECURITY_AVAILABLE, reason="Security layer not available in this repository snapshot")
def test_input_validator_catches_injection_in_api_params() -> None:
    from src.security.input_validator import InputValidator

    validator = InputValidator()
    assert validator.check_injection("'; DROP TABLE threats; --") is True
    assert validator.check_injection("patrol sector alpha") is False
    assert validator.check_injection("دورية القطاع ألفا") is False
    assert validator.check_path_traversal("../../etc/passwd") is True
    assert validator.check_path_traversal("models/phi3/model.gguf") is False


@pytest.mark.skipif(not SECURITY_AVAILABLE, reason="Security layer not available in this repository snapshot")
def test_secure_audit_log_chains_across_operations() -> None:
    from src.security.audit_log import SecureAuditLog

    audit = SecureAuditLog()
    for action in ["threat_detected", "llm_query", "decision_made", "command_issued", "path_planned"]:
        audit.log(action=action, details={"source": "integration"})
    report = audit.verify_chain()
    assert report["valid"] is True
    assert report["entries_checked"] == 5


@pytest.mark.skipif(not SECURITY_AVAILABLE, reason="Security layer not available in this repository snapshot")
def test_audit_tamper_detection() -> None:
    from src.security.audit_log import SecureAuditLog

    audit = SecureAuditLog()
    for action in ["a", "b", "c", "d", "e"]:
        audit.log(action=action, details={"source": "integration"})

    # Best-effort tamper simulation for implementations that expose file backing.
    if hasattr(audit, "_log_path"):
        with open(audit._log_path, "r+", encoding="utf-8") as handle:  # noqa: SLF001
            content = handle.read().replace('"action": "c"', '"action": "tampered"', 1)
            handle.seek(0)
            handle.write(content)
            handle.truncate()

    report = audit.verify_chain()
    assert report["valid"] is False


@pytest.mark.skipif(not SECURITY_AVAILABLE, reason="Security layer not available in this repository snapshot")
def test_classification_banner_on_responses() -> None:
    from src.security.classification import ClassificationBanner

    banner = ClassificationBanner("UNCLASSIFIED - FOUO")
    assert banner.get_level() == "UNCLASSIFIED - FOUO"
    assert "UNCLASSIFIED - FOUO" in banner.get_banner_html()


@pytest.mark.skipif(not SECURITY_AVAILABLE, reason="Security layer not available in this repository snapshot")
def test_compliance_checker_full_stack() -> None:
    from src.security.compliance import ComplianceChecker

    checker = ComplianceChecker()
    report = checker.run_full_check()
    assert "overall_status" in report
    assert "checks" in report
    assert all(all(k in check for k in ["id", "name", "status", "detail"]) for check in report["checks"])
