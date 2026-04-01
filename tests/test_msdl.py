"""Tests for MSDL parser/generator round-trip behavior."""

from __future__ import annotations

from datetime import datetime, timezone

from services.interop.models import ForceStructure, MSDLScenario, ORBATUnit
from services.interop.msdl import MSDLGenerator, MSDLParser


def _sample_force() -> ForceStructure:
    hq = ORBATUnit(
        unit_id="u-hq",
        name="HQ",
        designation="Headquarters",
        echelon="brigade",
        unit_type="headquarters",
        affiliation="friendly",
        parent_unit_id=None,
        subordinate_ids=["u-1"],
        country_code=178,
        nato_symbol="SFGPUCHQ---*****",
        strength=500,
        equipment=[],
        position=(24.7, 46.6),
        commander="COL A",
    )
    unit = ORBATUnit(
        unit_id="u-1",
        name="1st Battalion",
        designation="1st Battalion",
        echelon="battalion",
        unit_type="armor",
        affiliation="friendly",
        parent_unit_id="u-hq",
        subordinate_ids=[],
        country_code=178,
        nato_symbol="SFGPUCAA---*****",
        strength=700,
        equipment=[],
        position=(24.71, 46.61),
        commander="LTC B",
    )
    return ForceStructure(
        force_id="f1",
        force_name="Saudi Force",
        affiliation="friendly",
        units=[hq, unit],
        country_code=178,
    )


def test_generate_produces_military_scenario_root():
    generator = MSDLGenerator()
    scenario = MSDLScenario(
        scenario_id="s1",
        name="Scenario",
        description="Test scenario",
        forces=[_sample_force()],
        environment={"terrain": "desert", "weather": "clear"},
        overlay={"objectives": ["OBJ-1"]},
        version="1.0",
        created_at=datetime.now(timezone.utc),
    )
    xml = generator.generate(scenario)
    assert "<MilitaryScenario" in xml


def test_parser_reverses_generate_with_forces_preserved():
    generator = MSDLGenerator()
    parser = MSDLParser()
    scenario = MSDLScenario(
        scenario_id="s2",
        name="Scenario2",
        description="Roundtrip",
        forces=[_sample_force()],
        environment={"terrain": "desert"},
        overlay={"phase_lines": ["PL-A"]},
        version="1.0",
        created_at=datetime.now(timezone.utc),
    )
    xml = generator.generate(scenario)
    parsed = parser.parse(xml)
    assert parsed.scenario_id == "s2"
    assert len(parsed.forces) == 1
    assert parsed.forces[0].unit_count() >= 2


def test_generate_from_s3m_scenario_converts_payload():
    generator = MSDLGenerator()
    xml = generator.generate_from_s3m_scenario(
        {
            "scenario_id": "s3",
            "name": "From S3M",
            "forces": [
                {
                    "force_id": "f1",
                    "force_name": "Saudi",
                    "allegiance": "friendly",
                    "country_code": 178,
                    "units": [{"unit_id": "u1", "type": "armor", "count": 1, "position": [24.7, 46.6]}],
                }
            ],
        }
    )
    assert "<ForceSides>" in xml
    assert "<UnitID>u1</UnitID>" in xml


def test_unit_hierarchy_preserved_through_roundtrip():
    generator = MSDLGenerator()
    parser = MSDLParser()
    scenario = MSDLScenario(
        scenario_id="s4",
        name="Hierarchy",
        description="Hierarchy test",
        forces=[_sample_force()],
        environment={},
        overlay={},
        version="1.0",
        created_at=datetime.now(timezone.utc),
    )
    xml = generator.generate(scenario)
    parsed = parser.parse(xml)
    force = parsed.forces[0]
    hq = force.get_unit("u-hq")
    assert hq is not None
    assert "u-1" in hq.subordinate_ids


def test_parse_forces_extracts_expected_units_count():
    parser = MSDLParser()
    xml = (
        "<MilitaryScenario>"
        "<ScenarioID>x</ScenarioID>"
        "<ForceSides><ForceSide><ForceID>f</ForceID><ForceName>F</ForceName>"
        "<Affiliation>friendly</Affiliation><CountryCode>178</CountryCode>"
        "<Units><Unit><UnitID>u1</UnitID><Name>U1</Name><Designation>D1</Designation>"
        "<Echelon>company</Echelon><UnitType>infantry</UnitType><Affiliation>friendly</Affiliation>"
        "<CountryCode>178</CountryCode><NATOSymbol>A</NATOSymbol><Strength>100</Strength></Unit></Units>"
        "</ForceSide></ForceSides></MilitaryScenario>"
    )
    scenario = parser.parse(xml)
    assert len(scenario.forces) == 1
    assert scenario.forces[0].unit_count() == 1
