"""Tests for PersonnelRegistry in Phase 20 readiness layer."""

from __future__ import annotations

from apps.readiness.models import Branch, ClearanceLevel, MedicalStatus, MilitaryStatus, Rank
from apps.readiness.personnel.registry import PersonnelRegistry


def _registry() -> PersonnelRegistry:
    return PersonnelRegistry(max_personnel=1000)


def test_register_and_get_member():
    reg = _registry()
    m = reg.register(
        name_en="Ahmed Khan",
        name_ar="أحمد خان",
        rank=Rank.CAPTAIN,
        branch=Branch.ARMY,
        mos="11A",
        mos_description_en="Armor Officer",
        mos_description_ar="ضابط مدرعات",
        unit_id="u1",
        unit_name_en="1st Armored",
        unit_name_ar="المدرعات الأولى",
    )
    assert reg.get_member(m.member_id) is not None
    assert reg.get_by_service_number(m.service_number).member_id == m.member_id


def test_search_finds_by_name_en_and_name_ar():
    reg = _registry()
    reg.register(
        name_en="Ali Hassan",
        name_ar="علي حسن",
        rank=Rank.SERGEANT,
        branch=Branch.ARMY,
        mos="11B",
        mos_description_en="Infantry",
        mos_description_ar="مشاة",
        unit_id="u1",
        unit_name_en="Unit",
        unit_name_ar="وحدة",
    )
    assert len(reg.search("Ali")) >= 1
    assert len(reg.search("علي")) >= 1


def test_promote_updates_rank_and_date_of_rank():
    reg = _registry()
    m = reg.register(
        name_en="Omar",
        name_ar="عمر",
        rank=Rank.FIRST_LIEUTENANT,
        branch=Branch.ARMY,
        mos="11A",
        mos_description_en="Armor",
        mos_description_ar="مدرعات",
        unit_id="u1",
        unit_name_en="Unit",
        unit_name_ar="وحدة",
    )
    before = m.date_of_rank
    promoted = reg.promote(m.member_id, Rank.CAPTAIN)
    assert promoted.rank == Rank.CAPTAIN
    assert promoted.date_of_rank >= before


def test_update_status_medical_clearance():
    reg = _registry()
    m = reg.register(
        name_en="Majed",
        name_ar="ماجد",
        rank=Rank.SERGEANT,
        branch=Branch.ARMY,
        mos="11B",
        mos_description_en="Infantry",
        mos_description_ar="مشاة",
        unit_id="u1",
        unit_name_en="Unit",
        unit_name_ar="وحدة",
    )
    reg.update_status(m.member_id, MilitaryStatus.TRAINING)
    reg.update_medical(m.member_id, MedicalStatus.LIMITED_DUTY)
    reg.update_clearance(m.member_id, ClearanceLevel.SECRET)
    row = reg.get_member(m.member_id)
    assert row.status == MilitaryStatus.TRAINING
    assert row.medical == MedicalStatus.LIMITED_DUTY
    assert row.clearance == ClearanceLevel.SECRET


def test_get_members_filters():
    reg = _registry()
    reg.register(
        name_en="A",
        name_ar="أ",
        rank=Rank.CAPTAIN,
        branch=Branch.ARMY,
        mos="11A",
        mos_description_en="Armor",
        mos_description_ar="مدرعات",
        unit_id="u1",
        unit_name_en="One",
        unit_name_ar="واحد",
    )
    m2 = reg.register(
        name_en="B",
        name_ar="ب",
        rank=Rank.SERGEANT,
        branch=Branch.CYBER,
        mos="17C",
        mos_description_en="Cyber",
        mos_description_ar="سيبراني",
        unit_id="u2",
        unit_name_en="Two",
        unit_name_ar="اثنان",
        medical=MedicalStatus.LIMITED_DUTY,
    )
    by_unit = reg.get_members(unit_id="u1")
    by_rank = reg.get_members(rank=Rank.SERGEANT)
    by_branch = reg.get_members(branch=Branch.CYBER)
    deployable = reg.get_members(deployable_only=True)
    assert len(by_unit) == 1
    assert len(by_rank) == 1
    assert len(by_branch) == 1
    assert all(m.is_deployable() for m in deployable)
    assert m2.member_id not in [m.member_id for m in deployable]


def test_get_unit_roster_returns_only_unit_members():
    reg = _registry()
    reg.register(
        name_en="A",
        name_ar="أ",
        rank=Rank.CAPTAIN,
        branch=Branch.ARMY,
        mos="11A",
        mos_description_en="Armor",
        mos_description_ar="مدرعات",
        unit_id="x",
        unit_name_en="X",
        unit_name_ar="اكس",
    )
    reg.register(
        name_en="B",
        name_ar="ب",
        rank=Rank.CAPTAIN,
        branch=Branch.ARMY,
        mos="11A",
        mos_description_en="Armor",
        mos_description_ar="مدرعات",
        unit_id="y",
        unit_name_en="Y",
        unit_name_ar="واي",
    )
    assert len(reg.get_unit_roster("x")) == 1


def test_create_saudi_battalion_template_creates_45_personnel():
    reg = _registry()
    rows = reg.create_saudi_battalion_template()
    assert len(rows) == 45


def test_statistics_returns_counts():
    reg = _registry()
    reg.register(
        name_en="A",
        name_ar="أ",
        rank=Rank.CAPTAIN,
        branch=Branch.ARMY,
        mos="11A",
        mos_description_en="Armor",
        mos_description_ar="مدرعات",
        unit_id="u1",
        unit_name_en="One",
        unit_name_ar="واحد",
    )
    stats = reg.get_statistics()
    assert stats["total"] == 1
    assert stats["officers"] == 1
    assert "ARMY" in stats["by_branch"]
