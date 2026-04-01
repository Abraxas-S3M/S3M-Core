"""Unit tests for readiness certification manager."""

from __future__ import annotations

from datetime import timedelta, timezone, datetime

from apps.readiness.personnel import CertificationManager


def test_issue_and_get_member_certifications() -> None:
    cm = CertificationManager()
    cert = cm.issue_certification(
        member_id="m1",
        certification_type="UAV_OPERATOR",
        name_en="UAV Operator",
        name_ar="مشغل طائرات بدون طيار",
        issuing_authority="Saudi MOD",
    )
    assert cert.member_id == "m1"
    rows = cm.get_member_certifications("m1")
    assert len(rows) == 1
    assert rows[0].cert_id == cert.cert_id


def test_renew_extends_expiry() -> None:
    cm = CertificationManager()
    cert = cm.issue_certification(
        member_id="m1",
        certification_type="UAV_OPERATOR",
        name_en="UAV Operator",
        name_ar="مشغل طائرات بدون طيار",
        issuing_authority="Saudi MOD",
        expiry_days=1,
    )
    old_exp = cert.expiry_date
    cm.renew(cert.cert_id, new_expiry_days=365)
    assert cert.expiry_date > old_exp


def test_suspend_changes_status() -> None:
    cm = CertificationManager()
    cert = cm.issue_certification(
        member_id="m1",
        certification_type="S3M_CYBER_DEFENDER",
        name_en="Cyber Defense Analyst",
        name_ar="محلل الدفاع السيبراني",
        issuing_authority="S3M",
    )
    cm.suspend(cert.cert_id, "disciplinary hold")
    assert cert.status.value == "SUSPENDED"


def test_get_expiring_soon_window() -> None:
    cm = CertificationManager()
    near = cm.issue_certification(
        member_id="m1",
        certification_type="A",
        name_en="A",
        name_ar="أ",
        issuing_authority="X",
        expiry_days=7,
    )
    _far = cm.issue_certification(
        member_id="m1",
        certification_type="B",
        name_en="B",
        name_ar="ب",
        issuing_authority="X",
        expiry_days=120,
    )
    rows = cm.get_expiring_soon(30)
    assert any(c.cert_id == near.cert_id for c in rows)
    assert all((c.days_until_expiry() or 999) <= 30 for c in rows)


def test_get_expired_returns_past_expiry() -> None:
    cm = CertificationManager()
    cert = cm.issue_certification(
        member_id="m1",
        certification_type="A",
        name_en="A",
        name_ar="أ",
        issuing_authority="X",
        expiry_days=1,
    )
    cert.expiry_date = datetime.now(timezone.utc) - timedelta(days=1)
    rows = cm.get_expired()
    assert any(c.cert_id == cert.cert_id for c in rows)


def test_check_requirements_met_missing_expired() -> None:
    cm = CertificationManager()
    met = cm.issue_certification(
        member_id="m1",
        certification_type="S3M_WARGAMING_L1",
        name_en="Wargaming",
        name_ar="ألعاب حربية",
        issuing_authority="S3M",
    )
    expired = cm.issue_certification(
        member_id="m1",
        certification_type="UAV_OPERATOR",
        name_en="UAV",
        name_ar="طائرة بدون طيار",
        issuing_authority="S3M",
    )
    expired.expiry_date = datetime.now(timezone.utc) - timedelta(days=5)
    out = cm.check_requirements("m1", ["S3M_WARGAMING_L1", "UAV_OPERATOR", "S3M_CYBER_DEFENDER"])
    assert "S3M_WARGAMING_L1" in out["met"]
    assert "UAV_OPERATOR" in out["expired"]
    assert "S3M_CYBER_DEFENDER" in out["missing"]
    assert out["all_met"] is False


def test_create_standard_cert_types_bilingual_count() -> None:
    cm = CertificationManager()
    rows = cm.create_standard_cert_types()
    assert len(rows) == 10
    assert all("name_en" in r and "name_ar" in r for r in rows)
