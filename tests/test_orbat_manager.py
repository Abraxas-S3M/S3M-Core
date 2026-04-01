"""Tests for ORBAT manager and force structure workflows."""

from __future__ import annotations

from services.interop.msdl.orbat_manager import ORBATManager


def test_create_force_and_add_unit():
    manager = ORBATManager()
    force = manager.create_force("Blue Force", "friendly", 178)
    unit = manager.create_unit(
        name="Test Unit",
        designation="Test Unit",
        echelon="company",
        unit_type="infantry",
        affiliation="friendly",
    )
    manager.add_unit(force.force_id, unit)
    assert manager.get_force(force.force_id) is not None
    assert manager.get_unit(unit.unit_id) is not None


def test_build_hierarchy_nested_tree():
    manager = ORBATManager()
    force = manager.create_force("Blue Force", "friendly", 178)
    parent = manager.create_unit("Parent", "Parent", "battalion", "infantry", "friendly")
    manager.add_unit(force.force_id, parent)
    child = manager.create_unit(
        "Child",
        "Child",
        "company",
        "infantry",
        "friendly",
        parent_unit_id=parent.unit_id,
    )
    manager.add_unit(force.force_id, child)
    hierarchy = manager.build_hierarchy(force.force_id)
    assert hierarchy["hierarchy"][0]["unit"].unit_id == parent.unit_id
    assert hierarchy["hierarchy"][0]["subordinates"][0]["unit"].unit_id == child.unit_id


def test_create_saudi_template_complete_structure():
    manager = ORBATManager()
    force = manager.create_saudi_template()
    assert force.country_code == 178
    assert force.unit_count() >= 12
    assert any(unit.designation == "1st Armored Brigade" for unit in force.units)


def test_total_strength_sums_units():
    manager = ORBATManager()
    force = manager.create_force("Blue Force", "friendly", 178)
    u1 = manager.create_unit("U1", "U1", "company", "infantry", "friendly")
    u1.strength = 100
    u2 = manager.create_unit("U2", "U2", "company", "armor", "friendly")
    u2.strength = 200
    manager.add_unit(force.force_id, u1)
    manager.add_unit(force.force_id, u2)
    assert force.total_strength() == 300


def test_to_msdl_generates_xml():
    manager = ORBATManager()
    manager.create_saudi_template()
    xml = manager.to_msdl()
    assert "<MilitaryScenario>" in xml
    assert "<ForceSides>" in xml


def test_from_msdl_loads_forces():
    manager = ORBATManager()
    manager.create_saudi_template()
    xml = manager.to_msdl()
    other = ORBATManager()
    other.from_msdl(xml)
    assert len(other.get_all_forces()) >= 1
