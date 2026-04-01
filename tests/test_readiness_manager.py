"""Integration-style tests for ReadinessManager orchestration."""

from __future__ import annotations

from apps.readiness.manager import ReadinessManager
from apps.readiness.models import Branch, Rank


def test_full_pipeline_register_certify_assign_evaluate_score():
    mgr = ReadinessManager()
    member = mgr.register_member(
        name_en="Ali Al-Hamdi",
        name_ar="علي الحمدي",
        rank=Rank.CAPTAIN,
        branch=Branch.ARMY,
        mos="11A",
        mos_description_en="Armor Officer",
        mos_description_ar="ضابط مدرعات",
        unit_id="u1",
        unit_name_en="Unit 1",
        unit_name_ar="الوحدة 1",
    )
    mgr.issue_certification(
        member_id=member.member_id,
        certification_type="S3M_WARGAMING_L1",
        name_en="Wargaming Operator Level 1",
        name_ar="مشغل ألعاب حربية مستوى 1",
        issuing_authority="S3M Training Center",
    )
    unit = mgr.create_unit("Unit 1", "الوحدة 1", 1)
    mgr.personnel_registry.assign_to_unit(member.member_id, unit.unit_id, unit.unit_name_en, unit.unit_name_ar)
    slot = mgr.unit_manning_manager.add_slot(unit.unit_id, "XO", "ضابط تنفيذي", Rank.CAPTAIN, "11A")
    ok = mgr.fill_slot(slot.slot_id, member.member_id)
    assert ok is True

    eligibility = mgr.evaluate_eligibility(member.member_id)
    score = mgr.calculate_readiness(unit.unit_id)
    assert eligibility.member_id == member.member_id
    assert 0.0 <= score.overall_readiness <= 100.0


def test_create_saudi_battalion_returns_complete_unit():
    mgr = ReadinessManager()
    result = mgr.create_saudi_battalion()
    assert result["personnel"] == 45
    assert result["unit"]
    assert 0.0 <= result["fill_rate"] <= 100.0


def test_generate_readiness_report_returns_bilingual_text():
    mgr = ReadinessManager()
    out = mgr.generate_readiness_report()
    assert "EN" in out or "Force readiness report" in out
    assert "AR" in out or "تقرير" in out


def test_health_check_returns_subsystem_statuses():
    mgr = ReadinessManager()
    health = mgr.health_check()
    for key in [
        "status",
        "personnel_registry",
        "certification_manager",
        "unit_manning_manager",
        "eligibility_engine",
        "readiness_calculator",
        "coalition_bridge",
        "hr_adapter",
    ]:
        assert key in health
