"""Scenario engine for YAML-driven tactical exercise definitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4
import yaml

from src.simulation.models import EntityType, ForceComposition, ScenarioDefinition


class ScenarioEngine:
    """Load, validate, and build scenario definitions for wargaming runs."""

    def __init__(self, scenarios_dir: str = "configs/scenarios/") -> None:
        if not isinstance(scenarios_dir, str) or not scenarios_dir.strip():
            raise ValueError("scenarios_dir must be a non-empty string")
        self.scenarios_dir = Path(scenarios_dir)
        self.scenarios_dir.mkdir(parents=True, exist_ok=True)

    def load_from_yaml(self, filepath: str) -> ScenarioDefinition:
        """Load scenario definition from YAML file."""
        if not isinstance(filepath, str) or not filepath.strip():
            raise ValueError("filepath must be a non-empty string")
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"scenario file not found: {filepath}")
        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        return self.load_from_dict(payload)

    def _normalize_forces(self, raw_forces: List[Dict[str, Any]]) -> List[ForceComposition]:
        forces: List[ForceComposition] = []
        for raw_force in raw_forces:
            units: List[Dict[str, Any]] = []
            for raw_unit in raw_force.get("units", []):
                unit_type = raw_unit.get("type", EntityType.UNKNOWN.value)
                if not isinstance(unit_type, EntityType):
                    unit_type = EntityType(str(unit_type))
                position = raw_unit.get("position", raw_unit.get("starting_position", (0, 0, 0)))
                units.append(
                    {
                        "type": unit_type,
                        "count": int(raw_unit.get("count", 1)),
                        "starting_position": tuple(position),
                        "behavior": str(raw_unit.get("behavior", "hold")),
                    }
                )
            forces.append(
                ForceComposition(
                    force_name=str(raw_force.get("name", "Unnamed Force")),
                    allegiance=str(raw_force.get("allegiance", "friendly")).lower(),
                    units=units,
                )
            )
        return forces

    def load_from_dict(self, data: Dict[str, Any]) -> ScenarioDefinition:
        """Load scenario definition from raw dictionary payload."""
        if not isinstance(data, dict):
            raise ValueError("data must be a dictionary")
        raw = data.get("scenario", data)
        if not isinstance(raw, dict):
            raise ValueError("scenario payload must be a dictionary")

        name = str(raw.get("name", "Unnamed Scenario")).strip()
        scenario_id = str(raw.get("scenario_id", "")).strip() or f"scenario-{uuid4().hex[:12]}"
        forces = self._normalize_forces(list(raw.get("forces", [])))
        scenario = ScenarioDefinition(
            scenario_id=scenario_id,
            name=name,
            description=str(raw.get("description", "No description provided")).strip(),
            scenario_type=str(raw.get("type", raw.get("scenario_type", "custom"))).strip(),
            terrain=dict(raw.get("terrain", {})),
            weather=dict(raw.get("weather", {})),
            forces=forces,
            objectives=list(raw.get("objectives", [])),
            rules_of_engagement=str(raw.get("rules_of_engagement", "weapons_tight")),
            duration_seconds=int(raw.get("duration_seconds", 600)),
            parameters=dict(raw.get("parameters", {})),
        )
        ok, errors = self.validate_scenario(scenario)
        if not ok:
            raise ValueError(f"invalid scenario: {errors}")
        return scenario

    def list_scenarios(self) -> List[Dict[str, Any]]:
        """List available YAML scenarios with summary metadata."""
        results: List[Dict[str, Any]] = []
        for path in sorted(self.scenarios_dir.glob("*.yaml")):
            try:
                scenario = self.load_from_yaml(str(path))
                results.append(
                    {
                        "scenario_id": scenario.scenario_id,
                        "name": scenario.name,
                        "type": scenario.scenario_type,
                        "path": str(path),
                    }
                )
            except Exception:
                continue
        return results

    def validate_scenario(self, scenario: ScenarioDefinition) -> tuple[bool, List[str]]:
        """Validate tactical scenario constraints before execution."""
        if not isinstance(scenario, ScenarioDefinition):
            raise ValueError("scenario must be ScenarioDefinition")
        ok, errors = scenario.validate()
        if not scenario.forces:
            errors.append("scenario requires at least one force")
        if scenario.duration_seconds <= 0:
            errors.append("scenario duration must be > 0")
        if not scenario.objectives:
            errors.append("scenario requires at least one objective")
        return (len(errors) == 0, errors)

    def create_scenario(
        self,
        name,
        scenario_type,
        forces,
        objectives,
        terrain=None,
        weather=None,
        duration=600,
        roe="weapons_tight",
        parameters=None,
    ) -> ScenarioDefinition:
        """Create a scenario definition programmatically for tactical experiments."""
        if not isinstance(forces, list) or any(not isinstance(force, ForceComposition) for force in forces):
            raise ValueError("forces must be a list of ForceComposition")
        if not isinstance(objectives, list):
            raise ValueError("objectives must be a list")
        scenario = ScenarioDefinition(
            scenario_id=f"scenario-{uuid4().hex[:12]}",
            name=str(name),
            description=f"Programmatic scenario: {name}",
            scenario_type=str(scenario_type),
            terrain=dict(
                terrain
                or {
                    "bounds": [[0, 0, 0], [1000, 1000, 200]],
                    "type": "mixed",
                    "obstacles": [],
                }
            ),
            weather=dict(
                weather
                or {
                    "visibility": 1.0,
                    "wind_speed": 0.0,
                    "wind_direction": 0.0,
                    "precipitation": "none",
                }
            ),
            forces=forces,
            objectives=objectives,
            rules_of_engagement=str(roe),
            duration_seconds=int(duration),
            parameters=dict(parameters or {}),
        )
        ok, errors = self.validate_scenario(scenario)
        if not ok:
            raise ValueError(f"scenario validation failed: {errors}")
        return scenario
