"""Scenario authoring bridge from ORBAT/brief/MSDL to Phase 7 format."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List
from uuid import uuid4
from xml.etree import ElementTree as ET

from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class ScenarioAuthor:
    """Builds simulation-ready scenarios while preserving offline operation."""

    def __init__(self):
        self._orchestrator = Orchestrator()

    def _mk_units(self, prefix: str, count: int, x: float, y_offset: float) -> List[dict]:
        units = []
        for idx in range(count):
            units.append(
                {
                    "type": "ENEMY_INFANTRY" if prefix == "red" else "FRIENDLY_UGV",
                    "count": 1,
                    "position": (x, y_offset + idx * 12.0, 0.0),
                    "starting_position": (x, y_offset + idx * 12.0, 0.0),
                    "behavior": "patrol" if prefix == "blue" else "aggressive",
                }
            )
        return units

    def create_from_orbat(self, blue_force_id: str, red_force_id: str, terrain: str = "desert", weather: dict = None, duration_s: int = 600) -> dict:
        weather = weather or {"visibility": 0.9, "wind_speed": 8.0, "precipitation": "none"}
        scenario = {
            "scenario": {
                "scenario_id": f"scenario-{uuid4().hex[:10]}",
                "name": f"ORBAT Scenario {blue_force_id} vs {red_force_id}",
                "description": "Generated from ORBAT force references for tactical rehearsal.",
                "type": "orbat_generated",
                "terrain": {"type": terrain, "bounds": [[0, 0, 0], [200, 200, 50]]},
                "weather": weather,
                "forces": [
                    {"name": blue_force_id, "allegiance": "friendly", "units": self._mk_units("blue", 10, 20.0, 20.0)},
                    {"name": red_force_id, "allegiance": "enemy", "units": self._mk_units("red", 12, 170.0, 20.0)},
                ],
                "objectives": [
                    {"description": "Defend key terrain", "success_condition": "enemy_losses >= 5", "priority": 1},
                    {"description": "Preserve blue combat power", "success_condition": "friendly_losses <= 6", "priority": 1},
                ],
                "rules_of_engagement": "weapons_tight",
                "duration_seconds": int(duration_s),
                "parameters": {"source": "orbat", "generated_at": datetime.now(timezone.utc).isoformat()},
            }
        }
        return scenario

    def create_from_brief(self, brief: str) -> dict:
        prompt = (
            f"Create a military scenario definition from this brief: {brief}. Output JSON with: "
            "forces (blue and red with unit types, counts, positions), terrain, weather, objectives, ROE, duration."
        )
        try:
            response = self._orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.PLANNING))
            text = (getattr(response, "text", "") or "").strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:].strip()
            payload = json.loads(text)
            return {
                "scenario": {
                    "scenario_id": f"scenario-{uuid4().hex[:10]}",
                    "name": payload.get("name", "Brief Generated Scenario"),
                    "description": str(brief),
                    "type": "brief_generated",
                    "terrain": payload.get("terrain", {"type": "desert", "bounds": [[0, 0, 0], [200, 200, 50]]}),
                    "weather": payload.get("weather", {"visibility": 0.9, "wind_speed": 6.0, "precipitation": "none"}),
                    "forces": payload.get("forces", []),
                    "objectives": payload.get("objectives", [{"description": "Hold ground", "success_condition": "enemy_losses >= 4"}]),
                    "rules_of_engagement": payload.get("ROE", "weapons_tight"),
                    "duration_seconds": int(payload.get("duration", 600)),
                    "parameters": {"source": "brief"},
                }
            }
        except Exception:
            pass

        return {
            "scenario": {
                "scenario_id": f"scenario-{uuid4().hex[:10]}",
                "name": "Template Brief Scenario",
                "description": brief,
                "type": "brief_fallback",
                "terrain": {"type": "desert", "bounds": [[0, 0, 0], [200, 200, 50]]},
                "weather": {"visibility": 0.85, "wind_speed": 10.0, "precipitation": "none"},
                "forces": [
                    {"name": "Blue", "allegiance": "friendly", "units": self._mk_units("blue", 8, 20.0, 20.0)},
                    {"name": "Red", "allegiance": "enemy", "units": self._mk_units("red", 10, 170.0, 20.0)},
                ],
                "objectives": [{"description": "Delay enemy assault", "success_condition": "enemy_losses >= 5", "priority": 1}],
                "rules_of_engagement": "weapons_tight",
                "duration_seconds": 600,
                "parameters": {"source": "brief_fallback"},
            }
        }

    def create_from_msdl(self, msdl_xml: str) -> dict:
        root = ET.fromstring(msdl_xml)
        scenario_id = root.attrib.get("id", f"scenario-{uuid4().hex[:8]}")
        name = root.attrib.get("name", "MSDL Scenario")
        forces = []
        for force_el in root.findall(".//Force"):
            force_name = force_el.attrib.get("name", "Force")
            allegiance = force_el.attrib.get("allegiance", "friendly")
            units = []
            for unit_el in force_el.findall("Unit"):
                units.append(
                    {
                        "type": unit_el.attrib.get("type", "FRIENDLY_UGV"),
                        "count": int(unit_el.attrib.get("count", "1")),
                        "position": (
                            float(unit_el.attrib.get("x", "0")),
                            float(unit_el.attrib.get("y", "0")),
                            0.0,
                        ),
                        "starting_position": (
                            float(unit_el.attrib.get("x", "0")),
                            float(unit_el.attrib.get("y", "0")),
                            0.0,
                        ),
                        "behavior": unit_el.attrib.get("behavior", "hold"),
                    }
                )
            forces.append({"name": force_name, "allegiance": allegiance, "units": units})

        return {
            "scenario": {
                "scenario_id": scenario_id,
                "name": name,
                "description": "Converted from MSDL",
                "type": "msdl_converted",
                "terrain": {"type": "mixed", "bounds": [[0, 0, 0], [200, 200, 50]]},
                "weather": {"visibility": 1.0, "wind_speed": 5.0, "precipitation": "none"},
                "forces": forces,
                "objectives": [{"description": "Execute mission", "success_condition": "enemy_losses >= 1", "priority": 1}],
                "rules_of_engagement": "weapons_tight",
                "duration_seconds": 600,
                "parameters": {"source": "msdl"},
            }
        }

    def export_to_msdl(self, scenario: dict) -> str:
        payload = scenario.get("scenario", scenario)
        root = ET.Element("MSDL", attrib={"id": payload.get("scenario_id", "scenario"), "name": payload.get("name", "Scenario")})
        forces_el = ET.SubElement(root, "Forces")
        for force in payload.get("forces", []):
            force_el = ET.SubElement(
                forces_el,
                "Force",
                attrib={"name": str(force.get("name", "Force")), "allegiance": str(force.get("allegiance", "friendly"))},
            )
            for unit in force.get("units", []):
                pos = unit.get("position", unit.get("starting_position", (0.0, 0.0, 0.0)))
                ET.SubElement(
                    force_el,
                    "Unit",
                    attrib={
                        "type": str(unit.get("type", "UNKNOWN")),
                        "count": str(int(unit.get("count", 1))),
                        "x": str(float(pos[0])),
                        "y": str(float(pos[1])),
                        "behavior": str(unit.get("behavior", "hold")),
                    },
                )
        return ET.tostring(root, encoding="unicode")

    def get_scenario_templates(self) -> List[dict]:
        return [
            {"name": "Desert Patrol", "terrain": "desert", "description": "Open terrain patrol and interdiction."},
            {"name": "Urban Assault", "terrain": "urban", "description": "Dense urban close-quarters maneuver."},
            {"name": "Naval Blockade", "terrain": "open", "description": "Maritime denial and screening operations."},
            {"name": "Air Defense", "terrain": "mountain", "description": "Layered SAM and radar defense posture."},
            {"name": "Cyber+Kinetic Hybrid", "terrain": "mixed", "description": "Cyber disruption with kinetic exploitation."},
        ]
