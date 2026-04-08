#!/usr/bin/env python3
"""Populate Layer 06 dashboard with realistic offline sample data."""

from __future__ import annotations

import os
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.dashboard.providers.runtime_store import (
    set_agents,
    set_decisions,
    set_edge_models,
    set_formation,
    set_gps,
    set_jetson,
    set_missions,
    set_paths,
    set_simulation,
    set_sensors,
    set_threats,
)
from src.api.threat_routes import _sensor_manager, _threat_manager
from src.sensor_fusion.models import SensorType
from src.threat_detection.models import ThreatCategory, ThreatLevel


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(offset_seconds: int = 0) -> str:
    return (_now() - timedelta(seconds=offset_seconds)).isoformat()


def _sample_threats() -> List[Dict[str, object]]:
    levels = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    categories = ["CYBER", "KINETIC", "ELECTRONIC_WARFARE", "SURVEILLANCE", "HYBRID"]
    sources = ["NETWORK_IDS", "OBJECT_DETECTION", "ANOMALY_DETECTION", "SENSOR_FUSION", "MANUAL"]
    threats: List[Dict[str, object]] = []
    for i in range(20):
        level = levels[i % len(levels)]
        threats.append(
            {
                "id": f"thr-{i+1:03d}",
                "event_id": f"thr-{i+1:03d}",
                "timestamp": _iso(offset_seconds=i * 90),
                "level": level,
                "category": categories[i % len(categories)],
                "source": sources[i % len(sources)],
                "title": f"{level} tactical signal {i+1}",
                "description": "Automated layered threat signal for operator rehearsal.",
                "confidence": round(random.uniform(0.55, 0.97), 2),
                "location": {
                    "x": random.randint(80, 950),
                    "y": random.randint(80, 950),
                    "z": random.randint(0, 60),
                },
            }
        )
    return threats


def _sample_sensors() -> List[Dict[str, object]]:
    names = ["RADAR", "EO_CAMERA", "IR_CAMERA", "LIDAR", "RF_SPECTRUM"]
    sensors: List[Dict[str, object]] = []
    for i, sensor_type in enumerate(names, start=1):
        sensors.append(
            {
                "sensor_id": f"sensor-{i}",
                "type": sensor_type,
                "last_reading_time": _iso(offset_seconds=random.randint(5, 40)),
                "readings_count": 30 + i * 3,
                "status": "active",
            }
        )
    return sensors


def _sample_agents() -> List[Dict[str, object]]:
    roles = ["LEADER", "SCOUT", "INTERCEPTOR", "FOLLOWER", "FOLLOWER", "SCOUT"]
    states = ["ACTIVE", "EXECUTING", "ACTIVE", "IDLE", "RETURNING", "ACTIVE"]
    agents: List[Dict[str, object]] = []
    for i in range(6):
        agents.append(
            {
                "id": f"agent-{i+1}",
                "role": roles[i],
                "state": states[i],
                "position": (
                    120 + i * 120 + random.randint(-20, 20),
                    150 + (i % 3) * 170 + random.randint(-20, 20),
                    20 + random.randint(0, 40),
                ),
                "heading": float(random.randint(0, 359)),
                "battery": float(random.randint(42, 98)),
                "capability": "uav" if i % 2 == 0 else "ugv",
                "mission_name": "Border Sweep" if i < 3 else "Perimeter Watch",
                "last_heartbeat": _iso(offset_seconds=random.randint(1, 20)),
            }
        )
    return agents


def _sample_missions() -> List[Dict[str, object]]:
    return [
        {
            "id": "mission-001",
            "type": "recon",
            "status": "active",
            "assigned_agents": ["agent-1", "agent-2", "agent-3"],
            "progress_pct": 62.5,
            "duration": 1240.0,
            "waypoints_completed": 8,
        },
        {
            "id": "mission-002",
            "type": "perimeter_security",
            "status": "active",
            "assigned_agents": ["agent-4", "agent-5", "agent-6"],
            "progress_pct": 34.0,
            "duration": 760.0,
            "waypoints_completed": 3,
        },
    ]


def _sample_decisions() -> List[Dict[str, object]]:
    decisions: List[Dict[str, object]] = []
    for i in range(10):
        flagged = i in {2, 5, 8}
        decisions.append(
            {
                "id": f"dec-{i+1:03d}",
                "type": "route_adjustment" if i % 2 == 0 else "target_prioritization",
                "agent_id": f"agent-{(i % 6) + 1}",
                "confidence": round(random.uniform(0.58, 0.96), 2),
                "risk_score": round(random.uniform(0.22, 0.93), 2),
                "requires_review": flagged,
                "reasoning": "Autonomy policy selected option based on threat proximity and fuel margins.",
                "timestamp": _iso(offset_seconds=i * 70),
                "status": "pending",
                "context": "Sector-7 tactical engagement window",
            }
        )
    return decisions


def _sample_paths() -> List[Dict[str, object]]:
    return [
        {
            "path_id": "path-001",
            "agent_id": "agent-1",
            "status": "active",
            "waypoints": [
                {"x": 100, "y": 120, "z": 20},
                {"x": 240, "y": 280, "z": 24},
                {"x": 390, "y": 360, "z": 30},
                {"x": 530, "y": 410, "z": 30},
            ],
        },
        {
            "path_id": "path-002",
            "agent_id": "agent-4",
            "status": "active",
            "waypoints": [
                {"x": 820, "y": 760, "z": 5},
                {"x": 700, "y": 650, "z": 6},
                {"x": 560, "y": 520, "z": 8},
                {"x": 420, "y": 430, "z": 8},
            ],
        },
    ]


def main() -> None:
    random.seed(23)

    # Threat + sensor fusion feeds.
    threat_rows = _sample_threats()
    sensor_rows = _sample_sensors()
    set_threats(threat_rows)
    set_sensors(sensor_rows)

    # Also seed shared in-process managers so providers can read live objects.
    try:
        _threat_manager.clear_log()
    except Exception:
        pass
    for row in threat_rows:
        try:
            _threat_manager.ingest_manual(
                title=str(row.get("title", "Threat event")),
                description=str(row.get("description", "Dashboard demo threat")),
                level=str(row.get("level", ThreatLevel.INFO.name)),
                category=str(row.get("category", ThreatCategory.UNKNOWN.value)),
            )
        except Exception:
            continue

    for sensor in sensor_rows:
        sensor_id = str(sensor.get("sensor_id", "sensor-demo"))
        sensor_type = str(sensor.get("type", "RADAR"))
        try:
            _sensor_manager.register_sensor(sensor_id=sensor_id, sensor_type=SensorType.from_value(sensor_type))
        except Exception:
            pass
    for i in range(30):
        sensor_id = f"sensor-{(i % 5) + 1}"
        try:
            _sensor_manager.ingest(
                sensor_id=sensor_id,
                data={"classification": "vehicle", "x": 100 + i * 8, "y": 120 + i * 5, "z": 0},
                position=(100 + i * 8, 120 + i * 5, 0.0),
                confidence=0.75,
            )
        except Exception:
            continue
    try:
        _sensor_manager.process()
    except Exception:
        pass

    # Autonomy mission state and decisions.
    set_agents(_sample_agents())
    set_missions(_sample_missions())
    set_decisions(_sample_decisions())
    set_formation(
        {
            "type": "WEDGE",
            "spacing": 45.0,
            "positions": {
                "agent-1": "leader",
                "agent-2": "left_wing",
                "agent-3": "right_wing",
                "agent-4": "left_rear",
                "agent-5": "right_rear",
                "agent-6": "tail",
            },
            "score": 0.91,
        }
    )
    set_paths(_sample_paths())

    # Navigation + edge runtime status.
    set_gps(
        {
            "quality": "good",
            "satellites": 14,
            "mode": "gps_imu_fusion",
            "drift_m": 0.7,
            "last_fix": _iso(offset_seconds=2),
        }
    )
    set_jetson(
        {
            "gpu_util_pct": 63.0,
            "memory_pct": 48.0,
            "temperature_c": 67.5,
            "power_w": 34.0,
            "cuda_version": "12.x",
            "status": "simulated",
        }
    )
    set_edge_models(
        [
            {
                "name": "yolov8n-military-int8",
                "precision": "INT8",
                "latency_ms": 12.4,
                "memory_mb": 612.0,
                "status": "loaded",
            },
            {
                "name": "phi3-medium-q4",
                "precision": "Q4_K_M",
                "latency_ms": 58.2,
                "memory_mb": 4200.0,
                "status": "loaded",
            },
        ]
    )
    set_simulation({"running_scenarios": 0, "replay_count": 3, "datasets_generated": 7, "status": "idle"})

    print("Sample data loaded. Open http://localhost:8080/dashboard/ to view.")


if __name__ == "__main__":
    main()
