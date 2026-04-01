"""Tests for readiness deployment eligibility engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.readiness.models import (
    Branch,
    Certification,
    CertificationStatus,
    ClearanceLevel,
    DeploymentRecord,
    MedicalStatus,
    MilitaryStatus,
    Rank,
    ServiceMember,
)
from apps.readiness.units.eligibility_engine import EligibilityEngine


def _member(status=MilitaryStatus.ACTIVE_DUTY, medical=MedicalStatus.FIT_FOR_DUTY) -> ServiceMember:
    now = datetime.now(timezone.utc)
    return ServiceMember(
        member_id="m1",
        service_number="SN1",
        name_en="Ali",
        name_ar="علي",
        rank=Rank.CAPTAIN,
        branch=Branch.ARMY,
        mos="11A",
        mos_description_en="Armor Officer",
        mos_description_ar="ضابط مدرعات",
        status=status,
        clearance=ClearanceLevel.CONFIDENTIAL,
        medical=medical,
        unit_id="u1",
        unit_name_en="Unit 1",
        unit_name_ar="الوحدة 1",
        date_of_rank=now - timedelta(days=300),
        service_start_date=now - timedelta(days=365 * 4),
        years_of_service=4.0,
    )


def test_active_fit_cleared_eligible_green() -> None:
    engine = EligibilityEngine()
    result = engine.evaluate(_member())
    assert result.eligible is True
    assert result.overall_readiness == "green"


def test_medical_hold_not_eligible_red() -> None:
    engine = EligibilityEngine()
    result = engine.evaluate(_member(medical=MedicalStatus.LIMITED_DUTY))
    assert result.eligible is False
    assert result.overall_readiness == "red"
    assert "medical_fit" in result.disqualifiers


def test_deployed_status_not_eligible_red() -> None:
    engine = EligibilityEngine()
    result = engine.evaluate(_member(status=MilitaryStatus.DEPLOYED))
    assert result.eligible is False
    assert result.overall_readiness == "red"
    assert "active_duty" in result.disqualifiers


def test_expired_certs_eligible_but_amber() -> None:
    engine = EligibilityEngine()
    now = datetime.now(timezone.utc)
    cert = Certification(
        cert_id="c1",
        member_id="m1",
        certification_type="S3M_WARGAMING_L1",
        name_en="Cert",
        name_ar="شهادة",
        status=CertificationStatus.EXPIRED,
        issued_date=now - timedelta(days=400),
        expiry_date=now - timedelta(days=1),
        issuing_authority="S3M",
    )
    result = engine.evaluate(_member(), certifications=[cert])
    assert result.eligible is True
    assert result.overall_readiness == "amber"


def test_evaluate_unit_counts() -> None:
    engine = EligibilityEngine()
    rows = [
        _member(),
        _member(status=MilitaryStatus.DEPLOYED),
        _member(medical=MedicalStatus.LIMITED_DUTY),
    ]
    rows[0].unit_id = "u1"
    rows[1].unit_id = "u1"
    rows[2].unit_id = "u1"
    out = engine.evaluate_unit("u1", rows)
    assert out["total"] == 3
    assert out["green"] == 1
    assert out["red"] == 2


def test_generate_eligibility_report_returns_bilingual_text() -> None:
    engine = EligibilityEngine()
    member = _member()
    eligibility = engine.evaluate(member)
    report = engine.generate_eligibility_report(member, eligibility)
    assert "Eligibility" in report or "eligible" in report.lower()
    assert "تقرير" in report
