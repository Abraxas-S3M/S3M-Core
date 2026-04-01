"""Unit tests for readiness core dataclasses and enums."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apps.readiness.models import (
    Branch,
    Certification,
    CertificationStatus,
    ClearanceLevel,
    ManningSlot,
    MedicalStatus,
    MilitaryStatus,
    Rank,
    ReadinessLevel,
    ReadinessScore,
    ServiceMember,
    UnitManning,
)


def test_service_member_to_dict_and_safe_dict_strip_contact() -> None:
    member = ServiceMember(
        member_id="m1",
        service_number="KSA-1",
        name_en="Fahad",
        name_ar="فهد",
        rank=Rank.CAPTAIN,
        branch=Branch.ARMY,
        mos="11A",
        mos_description_en="Armor Officer",
        mos_description_ar="ضابط مدرعات",
        status=MilitaryStatus.ACTIVE_DUTY,
        clearance=ClearanceLevel.SECRET,
        medical=MedicalStatus.FIT_FOR_DUTY,
        unit_id="u1",
        unit_name_en="Unit 1",
        unit_name_ar="الوحدة 1",
        date_of_rank=datetime.now(timezone.utc) - timedelta(days=365),
        service_start_date=datetime.now(timezone.utc) - timedelta(days=365 * 5),
        years_of_service=5.0,
        contact={"phone": "+966500000000"},
    )
    raw = member.to_dict()
    safe = member.to_safe_dict()
    assert "contact" in raw
    assert "contact" not in safe
    assert safe["contact_redacted"] is True


def test_rank_is_officer_and_ordering() -> None:
    assert Rank.is_officer(Rank.CAPTAIN) is True
    assert Rank.is_officer(Rank.SERGEANT) is False
    assert Rank.rank_level(Rank.MAJOR) > Rank.rank_level(Rank.CAPTAIN)


def test_certification_valid_and_expiry_days() -> None:
    cert = Certification(
        cert_id="c1",
        member_id="m1",
        certification_type="UAV_OPERATOR",
        name_en="UAV Operator",
        name_ar="مشغل طائرات بدون طيار",
        status=CertificationStatus.ACTIVE,
        issued_date=datetime.now(timezone.utc) - timedelta(days=2),
        expiry_date=datetime.now(timezone.utc) + timedelta(days=10),
        issuing_authority="S3M",
    )
    assert cert.is_valid() is True
    days = cert.days_until_expiry()
    assert days is not None and days > 0


def test_manning_slot_vacant() -> None:
    slot = ManningSlot(
        slot_id="s1",
        unit_id="u1",
        position_title_en="Platoon Leader",
        position_title_ar="قائد فصيل",
        required_rank=Rank.FIRST_LIEUTENANT,
        required_mos="11A",
        required_clearance=ClearanceLevel.CONFIDENTIAL,
    )
    assert slot.is_vacant() is True
    slot.filled_by = "m1"
    slot.status = "filled"
    assert slot.is_vacant() is False


def test_unit_manning_fill_rate() -> None:
    unit = UnitManning(
        unit_id="u1",
        unit_name_en="1st Armored Battalion",
        unit_name_ar="كتيبة المدرعات الأولى",
        orbat_unit_id=None,
        authorized_strength=100,
        assigned_strength=75,
        slots=[],
    )
    assert unit.fill_rate() == 0.75


def test_readiness_score_creation() -> None:
    score = ReadinessScore(
        unit_id="u1",
        timestamp=datetime.now(timezone.utc),
        personnel_readiness=82.0,
        training_readiness=71.0,
        equipment_readiness=75.0,
        overall_readiness=76.0,
        readiness_level=ReadinessLevel.AMBER,
        manning_fill_rate=90.0,
        certification_rate=71.0,
        deployment_eligible_rate=82.0,
    )
    assert score.readiness_level == ReadinessLevel.AMBER
