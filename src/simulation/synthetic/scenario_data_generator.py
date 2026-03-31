"""Threat scenario generator producing labeled synthetic events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
import json
import random

from src.threat_detection.models import ThreatCategory, ThreatLevel, ThreatSource


class ScenarioDataGenerator:
    """Generate tactical threat timelines with ground-truth labels for model evaluation."""

    def __init__(self) -> None:
        self._rng = random.Random(23)

    def _event(
        self,
        ts: datetime,
        category: ThreatCategory,
        level: ThreatLevel,
        source: ThreatSource,
        desc: str,
        position: tuple[float, float, float],
        truth: bool,
    ) -> Dict[str, Any]:
        return {
            "timestamp": ts.isoformat(),
            "threat_source": source.value,
            "threat_level": level.name,
            "threat_category": category.value,
            "position": position,
            "description": desc,
            "ground_truth_label": truth,
        }

    def generate_threat_scenario(self, scenario_type: str = "ambush", n_events: int = 50) -> dict:
        """Generate one labeled sequence compatible with ThreatEvent-like records."""
        if not isinstance(scenario_type, str) or not scenario_type.strip():
            raise ValueError("scenario_type must be a non-empty string")
        if not isinstance(n_events, int) or n_events <= 0:
            raise ValueError("n_events must be > 0")

        scenario_type = scenario_type.strip().lower()
        ts = datetime.now(timezone.utc)
        events: List[Dict[str, Any]] = []
        truth: List[bool] = []

        for idx in range(n_events):
            event_time = ts + timedelta(seconds=idx * 3)
            is_true = self._rng.random() > 0.08
            truth.append(is_true)

            if scenario_type == "ambush":
                level = ThreatLevel.MEDIUM if idx < n_events // 3 else ThreatLevel.HIGH
                position = (500.0 + self._rng.uniform(-10, 10), 500.0 + self._rng.uniform(-10, 10), 0.0)
                event = self._event(
                    event_time,
                    ThreatCategory.KINETIC,
                    level,
                    ThreatSource.SENSOR_FUSION,
                    "Ambush fire concentration near chokepoint.",
                    position,
                    is_true,
                )
            elif scenario_type == "cyber_intrusion":
                phase = ["scan", "exploit", "lateral", "exfil"][min(3, idx * 4 // max(1, n_events))]
                level = ThreatLevel.LOW if phase == "scan" else ThreatLevel.HIGH if phase == "exfil" else ThreatLevel.MEDIUM
                event = self._event(
                    event_time,
                    ThreatCategory.CYBER,
                    level,
                    ThreatSource.NETWORK_IDS,
                    f"Cyber intrusion phase detected: {phase}.",
                    (0.0, 0.0, 0.0),
                    is_true,
                )
            elif scenario_type == "drone_swarm":
                angle = (idx / max(1, n_events)) * 6.28318
                position = (1000.0 + 400.0 * self._rng.uniform(0.8, 1.2), 1000.0 + 400.0 * self._rng.uniform(0.8, 1.2), 120.0)
                cat = ThreatCategory.SURVEILLANCE if idx < n_events // 2 else ThreatCategory.KINETIC
                level = ThreatLevel.HIGH if idx > n_events // 2 else ThreatLevel.MEDIUM
                event = self._event(
                    event_time,
                    cat,
                    level,
                    ThreatSource.OBJECT_DETECTION,
                    "Converging drone swarm signatures toward defended asset.",
                    position,
                    is_true,
                )
            elif scenario_type == "electronic_warfare":
                event = self._event(
                    event_time,
                    ThreatCategory.ELECTRONIC_WARFARE,
                    ThreatLevel.MEDIUM if idx < n_events // 2 else ThreatLevel.HIGH,
                    ThreatSource.ANOMALY_DETECTION,
                    "RF jamming pattern affecting tactical comms and GPS quality.",
                    (750.0 + self._rng.uniform(-80, 80), 300.0 + self._rng.uniform(-80, 80), 20.0),
                    is_true,
                )
            else:  # mixed
                category = self._rng.choice(
                    [
                        ThreatCategory.CYBER,
                        ThreatCategory.KINETIC,
                        ThreatCategory.ELECTRONIC_WARFARE,
                        ThreatCategory.SURVEILLANCE,
                    ]
                )
                source = self._rng.choice(
                    [
                        ThreatSource.NETWORK_IDS,
                        ThreatSource.OBJECT_DETECTION,
                        ThreatSource.ANOMALY_DETECTION,
                        ThreatSource.SENSOR_FUSION,
                    ]
                )
                level = self._rng.choice([ThreatLevel.LOW, ThreatLevel.MEDIUM, ThreatLevel.HIGH])
                event = self._event(
                    event_time,
                    category,
                    level,
                    source,
                    "Mixed-domain synthetic threat event.",
                    (
                        self._rng.uniform(0, 1200),
                        self._rng.uniform(0, 1200),
                        self._rng.uniform(0, 180),
                    ),
                    is_true,
                )
            events.append(event)

        stats = {
            "total_events": len(events),
            "true_positive": sum(1 for flag in truth if flag),
            "false_positive": sum(1 for flag in truth if not flag),
        }
        return {"events": events, "ground_truth": truth, "scenario_type": scenario_type, "stats": stats}

    def generate_detection_benchmark(self, n_scenarios: int = 10, events_per_scenario: int = 100) -> dict:
        """Generate a multi-scenario benchmark bundle for detection model testing."""
        if not isinstance(n_scenarios, int) or n_scenarios <= 0:
            raise ValueError("n_scenarios must be > 0")
        if not isinstance(events_per_scenario, int) or events_per_scenario <= 0:
            raise ValueError("events_per_scenario must be > 0")

        scenario_types = ["ambush", "cyber_intrusion", "drone_swarm", "electronic_warfare", "mixed"]
        rows: List[Dict[str, Any]] = []
        for idx in range(n_scenarios):
            stype = scenario_types[idx % len(scenario_types)]
            scenario = self.generate_threat_scenario(stype, events_per_scenario)
            for event in scenario["events"]:
                row = dict(event)
                row["scenario_id"] = f"benchmark-{idx:03d}"
                rows.append(row)
        return {
            "records": rows,
            "n_scenarios": n_scenarios,
            "events_per_scenario": events_per_scenario,
            "total_records": len(rows),
        }

    def save_scenarios(self, data: dict, filepath: str) -> str:
        """Save scenario data bundle to JSON file."""
        if not isinstance(data, dict):
            raise ValueError("data must be a dictionary")
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return str(path)
