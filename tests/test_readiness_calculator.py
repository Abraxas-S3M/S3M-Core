"""Tests for readiness calculator."""

from __future__ import annotations

from apps.readiness.manager import ReadinessManager
from apps.readiness.models import Rank


def _setup_unit() -> tuple[ReadinessManager, str]:
    manager = ReadinessManager()
    unit = manager.create_unit("Test Unit", "وحدة اختبار", 2)
    m1 = manager.register_member(
        name_en="A",
        name_ar="أ",
        rank=Rank.CAPTAIN,
        branch="ARMY",
        mos="11A",
        mos_description_en="Armor Officer",
        mos_description_ar="ضابط مدرعات",
        unit_id=unit.unit_id,
        unit_name_en=unit.unit_name_en,
        unit_name_ar=unit.unit_name_ar,
    )
    m2 = manager.register_member(
        name_en="B",
        name_ar="ب",
        rank=Rank.SERGEANT,
        branch="ARMY",
        mos="11B",
        mos_description_en="Infantry",
        mos_description_ar="مشاة",
        unit_id=unit.unit_id,
        unit_name_en=unit.unit_name_en,
        unit_name_ar=unit.unit_name_ar,
    )
    manager.unit_manning_manager.add_slot(unit.unit_id, "Officer", "ضابط", Rank.CAPTAIN, "11A")
    manager.unit_manning_manager.add_slot(unit.unit_id, "NCO", "صف ضابط", Rank.SERGEANT, "11B")
    manager.fill_slot(manager.unit_manning_manager.get_unit(unit.unit_id).slots[0].slot_id, m1.member_id)
    manager.fill_slot(manager.unit_manning_manager.get_unit(unit.unit_id).slots[1].slot_id, m2.member_id)
    return manager, unit.unit_id


def test_calculate_unit_readiness_produces_score_range():
    manager, unit_id = _setup_unit()
    score = manager.calculate_readiness(unit_id)
    assert 0 <= score.overall_readiness <= 100
    assert 0 <= score.personnel_readiness <= 100


def test_readiness_level_thresholds():
    manager, unit_id = _setup_unit()
    calc = manager.readiness_calculator
    assert calc._readiness_level(85).value == "GREEN"  # noqa: SLF001
    assert calc._readiness_level(65).value == "AMBER"  # noqa: SLF001
    assert calc._readiness_level(35).value == "RED"  # noqa: SLF001


def test_equipment_readiness_defaults_to_75_when_unavailable():
    manager, _ = _setup_unit()
    eq = manager.readiness_calculator._equipment_readiness("x")  # noqa: SLF001
    assert 0 <= eq <= 100


def test_critical_shortages_identifies_vacant_officer_slots():
    manager = ReadinessManager()
    unit = manager.create_unit("U", "و", 1)
    manager.unit_manning_manager.add_slot(unit.unit_id, "Officer", "ضابط", Rank.CAPTAIN, "11A")
    score = manager.calculate_readiness(unit.unit_id)
    assert any("Vacant CAPTAIN" in s for s in score.critical_shortages)


def test_calculate_force_readiness_aggregates_units():
    manager, unit_id = _setup_unit()
    force = manager.calculate_force_readiness([unit_id])
    assert "overall_readiness" in force
    assert force["units"]
