"""MSDL generation utilities from interop and simulation structures."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree as ET

from services.interop.models import ForceStructure, MSDLScenario, ORBATUnit


class MSDLGenerator:
    """Generates MSDL XML for scenario initialization and federation exchange."""

    def __init__(self):
        pass

    def generate(self, scenario: MSDLScenario) -> str:
        return scenario.to_xml()

    def generate_from_s3m_scenario(self, scenario_def) -> str:
        if hasattr(scenario_def, "to_dict"):
            payload = scenario_def.to_dict()
        elif isinstance(scenario_def, dict):
            payload = dict(scenario_def)
        else:
            payload = dict(getattr(scenario_def, "__dict__", {}))

        forces = []
        for force in payload.get("forces", []):
            units = []
            for unit in force.get("units", []):
                u = ORBATUnit(
                    unit_id=str(unit.get("unit_id", f"unit-{uuid4().hex[:8]}")),
                    name=str(unit.get("name", unit.get("type", "Unit"))),
                    designation=str(unit.get("designation", unit.get("name", "Unit"))),
                    echelon=str(unit.get("echelon", "company")),
                    unit_type=str(unit.get("unit_type", unit.get("type", "infantry"))).lower(),
                    affiliation=str(force.get("allegiance", "friendly")),
                    parent_unit_id=unit.get("parent_unit_id"),
                    subordinate_ids=list(unit.get("subordinate_ids", [])),
                    country_code=int(unit.get("country_code", 178)),
                    nato_symbol=str(unit.get("nato_symbol", "")),
                    strength=int(unit.get("strength", unit.get("count", 100))),
                    equipment=list(unit.get("equipment", [])),
                    position=tuple(unit.get("position")) if unit.get("position") else None,
                    commander=unit.get("commander"),
                )
                units.append(u)
            forces.append(
                ForceStructure(
                    force_id=str(force.get("force_id", f"force-{uuid4().hex[:8]}")),
                    force_name=str(force.get("force_name", force.get("force_name", "Force"))),
                    affiliation=str(force.get("allegiance", "friendly")),
                    units=units,
                    country_code=int(force.get("country_code", 178)),
                )
            )
        scenario = MSDLScenario(
            scenario_id=str(payload.get("scenario_id", f"scenario-{uuid4().hex[:8]}")),
            name=str(payload.get("name", "Generated Scenario")),
            description=str(payload.get("description", "Generated from S3M scenario definition")),
            forces=forces,
            environment=dict(
                payload.get("environment")
                or {
                    "terrain": payload.get("terrain", "desert"),
                    "weather": payload.get("weather", "clear"),
                    "time_of_day": payload.get("time_of_day", "0600"),
                }
            ),
            overlay=dict(payload.get("overlay", {})),
            version=str(payload.get("version", "1.0")),
            created_at=datetime.now(timezone.utc),
        )
        return scenario.to_xml()

    def generate_from_orbat(self, force: ForceStructure) -> str:
        root = ET.Element("MilitaryScenario")
        ET.SubElement(root, "ScenarioID").text = f"orbat-{uuid4().hex[:8]}"
        ET.SubElement(root, "Name").text = f"ORBAT Export - {force.force_name}"
        force_sides = ET.SubElement(root, "ForceSides")
        force_sides.append(ET.fromstring(force.to_msdl()))
        return ET.tostring(root, encoding="unicode")

