"""Tests for unit manning and slot assignment workflows."""

from __future__ import annotations

from apps.readiness.models import Branch, Rank
from apps.readiness.personnel.registry import PersonnelRegistry
from apps.readiness.units.manning_manager import UnitManningManager


def _registry_with_members() -> PersonnelRegistry:
    reg = PersonnelRegistry()
    reg.register(
        name_en="Captain Lead",
        name_ar="القائد",
        rank=Rank.CAPTAIN,
        branch=Branch.ARMY,
        mos="11A",
        mos_description_en="Armor Officer",
        mos_description_ar="ضابط مدرعات",
        unit_id="unit-1",
        unit_name_en="Unit 1",
        unit_name_ar="الوحدة 1",
    )
    reg.register(
        name_en="Sergeant Squad",
        name_ar="الرقيب",
        rank=Rank.SERGEANT,
        branch=Branch.ARMY,
        mos="11B",
        mos_description_en="Infantry",
        mos_description_ar="مشاة",
        unit_id="unit-1",
        unit_name_en="Unit 1",
        unit_name_ar="الوحدة 1",
    )
    return reg


def test_create_unit_with_slots() -> None:
    reg = _registry_with_members()
    mgr = UnitManningManager(personnel_registry=reg)
    unit = mgr.create_unit("1st Armored Battalion", "كتيبة المدرعات الأولى", 30)
    slot = mgr.add_slot(unit.unit_id, "Company Commander", "قائد سرية", Rank.CAPTAIN, "11A")
    assert unit.unit_id
    assert slot.slot_id
    assert len(unit.slots) == 1


def test_fill_slot_validates_rank_requirement() -> None:
    reg = _registry_with_members()
    mgr = UnitManningManager(personnel_registry=reg)
    unit = mgr.create_unit("Unit 1", "الوحدة 1", 10)
    slot = mgr.add_slot(unit.unit_id, "Commander", "قائد", Rank.MAJOR, "11A")
    captain = reg.search("Captain")[0]
    assert mgr.fill_slot(slot.slot_id, captain.member_id) is False


def test_fill_slot_validates_mos_requirement() -> None:
    reg = _registry_with_members()
    mgr = UnitManningManager(personnel_registry=reg)
    unit = mgr.create_unit("Unit 1", "الوحدة 1", 10)
    slot = mgr.add_slot(unit.unit_id, "Cyber Lead", "قائد سيبراني", Rank.SERGEANT, "17C")
    sergeant = reg.search("Sergeant")[0]
    assert mgr.fill_slot(slot.slot_id, sergeant.member_id) is False


def test_auto_fill_fills_matching_vacant_slots() -> None:
    reg = _registry_with_members()
    mgr = UnitManningManager(personnel_registry=reg)
    unit = mgr.create_unit("Unit 1", "الوحدة 1", 10)
    mgr.add_slot(unit.unit_id, "Commander", "قائد", Rank.CAPTAIN, "11A")
    mgr.add_slot(unit.unit_id, "Squad Lead", "قائد فصيلة", Rank.SERGEANT, "11B")
    result = mgr.auto_fill(unit.unit_id)
    assert result["filled"] == 2
    assert result["still_vacant"] == 0


def test_get_fill_rates_returns_correct_percentages() -> None:
    reg = _registry_with_members()
    mgr = UnitManningManager(personnel_registry=reg)
    unit = mgr.create_unit("Unit 1", "الوحدة 1", 4)
    slot = mgr.add_slot(unit.unit_id, "Commander", "قائد", Rank.CAPTAIN, "11A")
    captain = reg.search("Captain")[0]
    mgr.fill_slot(slot.slot_id, captain.member_id)
    rates = mgr.get_fill_rates()
    assert rates[unit.unit_id] == 0.25


def test_get_critical_vacancies_returns_officer_nco_vacancies() -> None:
    reg = _registry_with_members()
    mgr = UnitManningManager(personnel_registry=reg)
    unit = mgr.create_unit("Unit 1", "الوحدة 1", 10)
    mgr.add_slot(unit.unit_id, "Commander", "قائد", Rank.CAPTAIN, "11A")
    rows = mgr.get_critical_vacancies()
    assert len(rows) == 1
    assert rows[0]["required_rank"] == "CAPTAIN"


def test_create_from_orbat_builds_manning_from_phase16_orbat() -> None:
    reg = _registry_with_members()
    mgr = UnitManningManager(personnel_registry=reg)
    unit = mgr.create_from_orbat("orbat-test-1")
    assert unit.orbat_unit_id == "orbat-test-1"
    assert len(unit.slots) >= 29
