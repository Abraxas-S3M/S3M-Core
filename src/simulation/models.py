"""Core data models for S3M Layer 04 simulation and wargaming."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from math import sqrt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import hashlib


class SimulatorStatus(str, Enum):
    """Lifecycle state for simulator adapter connectivity and execution."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"


class EntityType(str, Enum):
    """Entity categories used across all simulation backends."""

    FRIENDLY_UAV = "FRIENDLY_UAV"
    FRIENDLY_UGV = "FRIENDLY_UGV"
    FRIENDLY_SHIP = "FRIENDLY_SHIP"
    ENEMY_UAV = "ENEMY_UAV"
    ENEMY_UGV = "ENEMY_UGV"
    ENEMY_SHIP = "ENEMY_SHIP"
    ENEMY_INFANTRY = "ENEMY_INFANTRY"
    CIVILIAN = "CIVILIAN"
    OBSTACLE = "OBSTACLE"
    WAYPOINT = "WAYPOINT"
    BASE = "BASE"
    UNKNOWN = "UNKNOWN"


@dataclass
class SimEntity:
    """Unified simulation entity record for tactical forces and environment."""

    entity_id: str
    entity_type: EntityType
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    heading: float
    health: float
    active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.entity_id, str) or not self.entity_id.strip():
            raise ValueError("entity_id must be a non-empty string")
        if not isinstance(self.entity_type, EntityType):
            self.entity_type = EntityType(str(self.entity_type))
        if not (isinstance(self.position, tuple) and len(self.position) == 3):
            raise ValueError("position must be a tuple of (x, y, z)")
        if not (isinstance(self.velocity, tuple) and len(self.velocity) == 3):
            raise ValueError("velocity must be a tuple of (vx, vy, vz)")
        if not all(isinstance(v, (int, float)) for v in self.position + self.velocity):
            raise ValueError("position and velocity must be numeric")
        self.position = (float(self.position[0]), float(self.position[1]), float(self.position[2]))
        self.velocity = (float(self.velocity[0]), float(self.velocity[1]), float(self.velocity[2]))
        if not isinstance(self.heading, (int, float)):
            raise ValueError("heading must be numeric")
        self.heading = float(self.heading)
        if not isinstance(self.health, (int, float)):
            raise ValueError("health must be numeric")
        self.health = max(0.0, min(1.0, float(self.health)))
        if not isinstance(self.active, bool):
            raise ValueError("active must be boolean")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize entity for API responses, replay files, and audit logs."""
        payload = asdict(self)
        payload["entity_type"] = self.entity_type.value
        return payload

    def distance_to(self, other: "SimEntity") -> float:
        """Compute Euclidean separation for collision and engagement logic."""
        if not isinstance(other, SimEntity):
            raise ValueError("other must be SimEntity")
        dx = self.position[0] - other.position[0]
        dy = self.position[1] - other.position[1]
        dz = self.position[2] - other.position[2]
        return sqrt(dx * dx + dy * dy + dz * dz)


@dataclass
class SimulationState:
    """Unified simulator snapshot shared with threat and autonomy pipelines."""

    timestamp: datetime
    sim_time_seconds: float
    entities: List[SimEntity] = field(default_factory=list)
    terrain: Dict[str, Any] = field(default_factory=dict)
    weather: Dict[str, Any] = field(default_factory=dict)
    active_events: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be datetime")
        if not isinstance(self.sim_time_seconds, (int, float)):
            raise ValueError("sim_time_seconds must be numeric")
        self.sim_time_seconds = max(0.0, float(self.sim_time_seconds))
        if not isinstance(self.entities, list) or any(not isinstance(e, SimEntity) for e in self.entities):
            raise ValueError("entities must be a list of SimEntity")
        if not isinstance(self.terrain, dict):
            raise ValueError("terrain must be a dictionary")
        if not isinstance(self.weather, dict):
            raise ValueError("weather must be a dictionary")
        if not isinstance(self.active_events, list):
            raise ValueError("active_events must be a list")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize state snapshot for streaming replay and API."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "sim_time_seconds": self.sim_time_seconds,
            "entities": [entity.to_dict() for entity in self.entities],
            "terrain": self.terrain,
            "weather": self.weather,
            "active_events": self.active_events,
            "metadata": self.metadata,
        }

    def get_entity(self, entity_id: str) -> Optional[SimEntity]:
        """Find entity by identifier inside current battlespace state."""
        if not isinstance(entity_id, str) or not entity_id.strip():
            return None
        for entity in self.entities:
            if entity.entity_id == entity_id:
                return entity
        return None

    def get_entities_by_type(self, entity_type: EntityType) -> List[SimEntity]:
        """Return entities of an exact type for tactical filtering."""
        if not isinstance(entity_type, EntityType):
            entity_type = EntityType(str(entity_type))
        return [entity for entity in self.entities if entity.entity_type == entity_type]

    def friendly_entities(self) -> List[SimEntity]:
        """Return all friendly entities for blue-force mission metrics."""
        return [entity for entity in self.entities if entity.entity_type.value.startswith("FRIENDLY_")]

    def enemy_entities(self) -> List[SimEntity]:
        """Return all enemy entities for red-force threat conversion."""
        return [entity for entity in self.entities if entity.entity_type.value.startswith("ENEMY_")]

    def to_threat_events(self) -> List[Any]:
        """Convert enemy entities to Layer 02 ThreatEvent objects."""
        from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource

        level_map = {
            EntityType.ENEMY_UAV: ThreatLevel.HIGH,
            EntityType.ENEMY_SHIP: ThreatLevel.HIGH,
            EntityType.ENEMY_INFANTRY: ThreatLevel.MEDIUM,
            EntityType.ENEMY_UGV: ThreatLevel.MEDIUM,
        }
        category_map = {
            EntityType.ENEMY_UAV: ThreatCategory.SURVEILLANCE,
            EntityType.ENEMY_SHIP: ThreatCategory.KINETIC,
            EntityType.ENEMY_INFANTRY: ThreatCategory.KINETIC,
            EntityType.ENEMY_UGV: ThreatCategory.KINETIC,
        }
        events: List[ThreatEvent] = []
        for entity in self.enemy_entities():
            level = level_map.get(entity.entity_type, ThreatLevel.LOW)
            category = category_map.get(entity.entity_type, ThreatCategory.UNKNOWN)
            events.append(
                ThreatEvent(
                    source=ThreatSource.SENSOR_FUSION,
                    level=level,
                    category=category,
                    title=f"Simulated {entity.entity_type.value} detected",
                    description=(
                        "Layer 04 generated adversary contact for tactical rehearsal at "
                        f"{tuple(round(v, 2) for v in entity.position)}"
                    ),
                    raw_data={
                        "entity_id": entity.entity_id,
                        "entity_type": entity.entity_type.value,
                        "velocity": entity.velocity,
                        "heading": entity.heading,
                        "health": entity.health,
                    },
                    confidence=max(0.2, min(1.0, entity.health)),
                    location={
                        "x": entity.position[0],
                        "y": entity.position[1],
                        "z": entity.position[2],
                        "sim_time_seconds": self.sim_time_seconds,
                    },
                    asset_ids=[entity.entity_id],
                    recommended_action="Track and classify contact before mission commander engagement decision.",
                )
            )
        return events

    def to_sensor_readings(self) -> List[Any]:
        """Convert entities to synthetic SensorReading objects for fusion tests."""
        from src.sensor_fusion.models import SensorReading, SensorType

        readings: List[SensorReading] = []
        for entity in self.entities:
            readings.append(
                SensorReading(
                    sensor_id=f"sim-sensor-{entity.entity_id[:8]}",
                    sensor_type=SensorType.RADAR,
                    timestamp=self.timestamp,
                    data={
                        "entity_id": entity.entity_id,
                        "entity_type": entity.entity_type.value,
                        "velocity": entity.velocity,
                        "heading": entity.heading,
                        "health": entity.health,
                        "active": entity.active,
                        "sim_time_seconds": self.sim_time_seconds,
                    },
                    position=entity.position,
                    confidence=max(0.1, min(1.0, entity.health)),
                )
            )
        return readings


@dataclass
class SimConfig:
    """Connection/runtime settings for a simulator adapter."""

    simulator_name: str
    host: str = "localhost"
    port: int = 0
    world_file: Optional[str] = None
    real_time_factor: float = 1.0
    headless: bool = True
    gpu_enabled: bool = True
    extra_params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.simulator_name, str) or not self.simulator_name.strip():
            raise ValueError("simulator_name must be a non-empty string")
        if not isinstance(self.host, str) or not self.host.strip():
            raise ValueError("host must be a non-empty string")
        if not isinstance(self.port, int) or not (0 <= self.port <= 65535):
            raise ValueError("port must be between 0 and 65535")
        if self.world_file is not None and not isinstance(self.world_file, str):
            raise ValueError("world_file must be a string or None")
        if not isinstance(self.real_time_factor, (int, float)) or float(self.real_time_factor) <= 0:
            raise ValueError("real_time_factor must be positive")
        self.real_time_factor = float(self.real_time_factor)
        if not isinstance(self.headless, bool):
            raise ValueError("headless must be boolean")
        if not isinstance(self.gpu_enabled, bool):
            raise ValueError("gpu_enabled must be boolean")
        if not isinstance(self.extra_params, dict):
            raise ValueError("extra_params must be a dictionary")


class ScenarioStatus(str, Enum):
    """Lifecycle status for scenario loading and execution."""

    DRAFT = "DRAFT"
    LOADED = "LOADED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


@dataclass
class ForceComposition:
    """Military force package defining units for one side in a scenario."""

    force_name: str
    allegiance: str
    units: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.force_name, str) or not self.force_name.strip():
            raise ValueError("force_name must be a non-empty string")
        if self.allegiance not in {"friendly", "enemy"}:
            raise ValueError("allegiance must be 'friendly' or 'enemy'")
        if not isinstance(self.units, list):
            raise ValueError("units must be a list")
        normalized: List[Dict[str, Any]] = []
        for unit in self.units:
            if not isinstance(unit, dict):
                raise ValueError("each unit must be a dictionary")
            unit_type = unit.get("type", EntityType.UNKNOWN)
            if not isinstance(unit_type, EntityType):
                unit_type = EntityType(str(unit_type))
            count = int(unit.get("count", 0))
            if count <= 0:
                raise ValueError("unit count must be > 0")
            pos = unit.get("starting_position", unit.get("position", (0.0, 0.0, 0.0)))
            if isinstance(pos, list):
                pos = tuple(pos)
            if not isinstance(pos, tuple) or len(pos) != 3:
                raise ValueError("starting_position must be length-3 tuple/list")
            behavior = str(unit.get("behavior", "hold")).strip() or "hold"
            normalized.append(
                {
                    "type": unit_type,
                    "count": count,
                    "starting_position": (float(pos[0]), float(pos[1]), float(pos[2])),
                    "behavior": behavior,
                }
            )
        self.units = normalized

    def to_dict(self) -> Dict[str, Any]:
        """Serialize force composition for YAML/API interoperability."""
        return {
            "force_name": self.force_name,
            "allegiance": self.allegiance,
            "units": [
                {
                    "type": unit["type"].value,
                    "count": unit["count"],
                    "starting_position": unit["starting_position"],
                    "behavior": unit["behavior"],
                }
                for unit in self.units
            ],
        }


@dataclass
class ScenarioDefinition:
    """Full scenario package used to run tactical exercises in Layer 04."""

    scenario_id: str
    name: str
    description: str
    scenario_type: str
    terrain: Dict[str, Any]
    weather: Dict[str, Any]
    forces: List[ForceComposition]
    objectives: List[Dict[str, Any]]
    rules_of_engagement: str
    duration_seconds: int
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise ValueError("scenario_id must be a non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("description must be a non-empty string")
        if not isinstance(self.scenario_type, str) or not self.scenario_type.strip():
            raise ValueError("scenario_type must be a non-empty string")
        if not isinstance(self.terrain, dict):
            raise ValueError("terrain must be a dictionary")
        if not isinstance(self.weather, dict):
            raise ValueError("weather must be a dictionary")
        if not isinstance(self.forces, list) or any(not isinstance(force, ForceComposition) for force in self.forces):
            raise ValueError("forces must be a list of ForceComposition")
        if not isinstance(self.objectives, list):
            raise ValueError("objectives must be a list")
        if not isinstance(self.rules_of_engagement, str) or not self.rules_of_engagement.strip():
            raise ValueError("rules_of_engagement must be a non-empty string")
        if not isinstance(self.duration_seconds, int) or self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be a positive integer")
        if not isinstance(self.parameters, dict):
            raise ValueError("parameters must be a dictionary")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize scenario for adapters and REST interfaces."""
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "scenario_type": self.scenario_type,
            "terrain": self.terrain,
            "weather": self.weather,
            "forces": [force.to_dict() for force in self.forces],
            "objectives": self.objectives,
            "rules_of_engagement": self.rules_of_engagement,
            "duration_seconds": self.duration_seconds,
            "parameters": self.parameters,
        }

    def total_units(self) -> int:
        """Total unit count across all forces."""
        return sum(unit["count"] for force in self.forces for unit in force.units)

    def validate(self) -> tuple[bool, List[str]]:
        """Validate scenario integrity and tactical bounds."""
        errors: List[str] = []
        if not self.forces:
            errors.append("scenario must define at least one force")
        if not self.objectives:
            errors.append("scenario must define at least one objective")
        if self.duration_seconds <= 0:
            errors.append("duration_seconds must be > 0")

        bounds = self.terrain.get("bounds")
        if bounds is not None:
            try:
                min_bound = tuple(bounds[0])
                max_bound = tuple(bounds[1])
                if len(min_bound) != 3 or len(max_bound) != 3:
                    errors.append("terrain bounds must include two xyz points")
                else:
                    for force in self.forces:
                        for unit in force.units:
                            px, py, pz = unit["starting_position"]
                            if not (min_bound[0] <= px <= max_bound[0]):
                                errors.append(f"{force.force_name} unit x out of terrain bounds")
                            if not (min_bound[1] <= py <= max_bound[1]):
                                errors.append(f"{force.force_name} unit y out of terrain bounds")
                            if not (min_bound[2] <= pz <= max_bound[2]):
                                errors.append(f"{force.force_name} unit z out of terrain bounds")
            except Exception:
                errors.append("terrain bounds must be [[minx,miny,minz],[maxx,maxy,maxz]]")

        for objective in self.objectives:
            if not isinstance(objective, dict):
                errors.append("each objective must be a dictionary")
                continue
            if not objective.get("description"):
                errors.append("objective missing description")
            if not objective.get("success_condition"):
                errors.append("objective missing success_condition")
        return (len(errors) == 0, errors)


@dataclass
class AARReport:
    """After Action Review generated from scenario execution outcomes."""

    aar_id: str
    scenario_id: str
    timestamp: datetime
    duration_seconds: float
    outcome: str
    friendly_losses: int
    enemy_losses: int
    objectives_met: List[str]
    objectives_failed: List[str]
    timeline: List[Dict[str, Any]]
    llm_analysis: Optional[str] = None
    lessons_learned: List[str] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.aar_id, str) or not self.aar_id.strip():
            raise ValueError("aar_id must be a non-empty string")
        if not isinstance(self.scenario_id, str) or not self.scenario_id.strip():
            raise ValueError("scenario_id must be a non-empty string")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be datetime")
        if not isinstance(self.duration_seconds, (int, float)) or float(self.duration_seconds) < 0:
            raise ValueError("duration_seconds must be non-negative")
        self.duration_seconds = float(self.duration_seconds)
        if self.outcome not in {"victory", "defeat", "draw", "incomplete"}:
            raise ValueError("outcome must be one of victory/defeat/draw/incomplete")
        if not isinstance(self.friendly_losses, int) or self.friendly_losses < 0:
            raise ValueError("friendly_losses must be non-negative integer")
        if not isinstance(self.enemy_losses, int) or self.enemy_losses < 0:
            raise ValueError("enemy_losses must be non-negative integer")
        if not isinstance(self.objectives_met, list):
            raise ValueError("objectives_met must be a list")
        if not isinstance(self.objectives_failed, list):
            raise ValueError("objectives_failed must be a list")
        if not isinstance(self.timeline, list):
            raise ValueError("timeline must be a list")
        if self.llm_analysis is not None and not isinstance(self.llm_analysis, str):
            raise ValueError("llm_analysis must be string or None")
        if not isinstance(self.lessons_learned, list):
            raise ValueError("lessons_learned must be a list")
        if not isinstance(self.statistics, dict):
            raise ValueError("statistics must be a dictionary")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize AAR report for API and archival persistence."""
        return {
            "aar_id": self.aar_id,
            "scenario_id": self.scenario_id,
            "timestamp": self.timestamp.isoformat(),
            "duration_seconds": self.duration_seconds,
            "outcome": self.outcome,
            "friendly_losses": self.friendly_losses,
            "enemy_losses": self.enemy_losses,
            "objectives_met": self.objectives_met,
            "objectives_failed": self.objectives_failed,
            "timeline": self.timeline,
            "llm_analysis": self.llm_analysis,
            "lessons_learned": self.lessons_learned,
            "statistics": self.statistics,
        }

    def summary(self) -> str:
        """Operational summary line for commander-level debriefs."""
        return (
            f"AAR {self.aar_id}: outcome={self.outcome}, "
            f"friendly_losses={self.friendly_losses}, enemy_losses={self.enemy_losses}"
        )


@dataclass
class ReplayArtifact:
    """Metadata describing a replay recording artifact on disk."""

    replay_id: str
    scenario_id: Optional[str]
    simulator: str
    created_at: datetime
    duration_seconds: float
    tick_count: int
    filepath: str
    file_size_bytes: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.replay_id, str) or not self.replay_id.strip():
            raise ValueError("replay_id must be a non-empty string")
        if self.scenario_id is not None and not isinstance(self.scenario_id, str):
            raise ValueError("scenario_id must be string or None")
        if not isinstance(self.simulator, str) or not self.simulator.strip():
            raise ValueError("simulator must be a non-empty string")
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be datetime")
        if not isinstance(self.duration_seconds, (int, float)) or float(self.duration_seconds) < 0:
            raise ValueError("duration_seconds must be non-negative")
        self.duration_seconds = float(self.duration_seconds)
        if not isinstance(self.tick_count, int) or self.tick_count < 0:
            raise ValueError("tick_count must be non-negative integer")
        if not isinstance(self.filepath, str) or not self.filepath.strip():
            raise ValueError("filepath must be non-empty string")
        if not isinstance(self.file_size_bytes, int) or self.file_size_bytes < 0:
            raise ValueError("file_size_bytes must be non-negative integer")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize replay artifact metadata."""
        return {
            "replay_id": self.replay_id,
            "scenario_id": self.scenario_id,
            "simulator": self.simulator,
            "created_at": self.created_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "tick_count": self.tick_count,
            "filepath": self.filepath,
            "file_size_bytes": self.file_size_bytes,
            "metadata": self.metadata,
        }


@dataclass
class SyntheticDataset:
    """Metadata for synthetic datasets generated by Layer 04 tools."""

    dataset_id: str
    name: str
    description: str
    generator: str
    created_at: datetime
    record_count: int
    file_path: str
    file_size_bytes: int
    checksum_sha256: str
    schema: Dict[str, Any]
    generation_params: Dict[str, Any]
    license: str

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, str) or not self.dataset_id.strip():
            raise ValueError("dataset_id must be non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be non-empty string")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("description must be non-empty string")
        if not isinstance(self.generator, str) or not self.generator.strip():
            raise ValueError("generator must be non-empty string")
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be datetime")
        if not isinstance(self.record_count, int) or self.record_count < 0:
            raise ValueError("record_count must be non-negative integer")
        if not isinstance(self.file_path, str) or not self.file_path.strip():
            raise ValueError("file_path must be non-empty string")
        if not isinstance(self.file_size_bytes, int) or self.file_size_bytes < 0:
            raise ValueError("file_size_bytes must be non-negative integer")
        if not isinstance(self.checksum_sha256, str) or len(self.checksum_sha256.strip()) < 16:
            raise ValueError("checksum_sha256 must be a hash-like string")
        if not isinstance(self.schema, dict):
            raise ValueError("schema must be a dictionary")
        if not isinstance(self.generation_params, dict):
            raise ValueError("generation_params must be a dictionary")
        if not isinstance(self.license, str) or not self.license.strip():
            raise ValueError("license must be non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize dataset metadata for manifest and API catalog responses."""
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "description": self.description,
            "generator": self.generator,
            "created_at": self.created_at.isoformat(),
            "record_count": self.record_count,
            "file_path": self.file_path,
            "file_size_bytes": self.file_size_bytes,
            "checksum_sha256": self.checksum_sha256,
            "schema": self.schema,
            "generation_params": self.generation_params,
            "license": self.license,
        }

    def verify_checksum(self) -> bool:
        """Recompute SHA-256 checksum to guarantee data integrity."""
        file_path = Path(self.file_path)
        if not file_path.exists() or not file_path.is_file():
            return False
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest().lower() == self.checksum_sha256.lower()
