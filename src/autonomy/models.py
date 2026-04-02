"""Core autonomy models for Layer 03 tactical decision systems.

These dataclasses define the shared contract between reinforcement learning,
behavior trees, swarm coordination, and explainability subsystems used in
contested military operating environments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Tuple


class AgentRole(Enum):
    """Operational role used for multi-agent tactical coordination."""

    LEADER = "leader"
    FOLLOWER = "follower"
    SCOUT = "scout"
    INTERCEPTOR = "interceptor"
    RELAY = "relay"
    RESERVE = "reserve"


class AgentState(Enum):
    """Mission readiness state for autonomous tactical platforms."""

    IDLE = "idle"
    ACTIVE = "active"
    EXECUTING = "executing"
    RETURNING = "returning"
    LOST = "lost"
    DESTROYED = "destroyed"
    MAINTENANCE = "maintenance"


class AgentCapability(Enum):
    """Primary warfighting domain for an autonomous agent."""

    AIR = "air"
    GROUND = "ground"
    MARITIME = "maritime"
    CYBER = "cyber"
    ELECTRONIC_WARFARE = "electronic_warfare"


@dataclass
class AgentInfo:
    """Live platform state used for missioning and survivability decisions."""

    agent_id: str
    role: AgentRole
    state: AgentState
    capability: AgentCapability
    position: Tuple[float, float, float]
    heading: float
    speed: float
    battery_pct: float
    fuel_pct: float
    current_mission: Optional[str] = None
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sensor_loadout: List[str] = field(default_factory=list)
    weapon_loadout: List[str] = field(default_factory=list)
    comms_status: str = "nominal"

    def __post_init__(self) -> None:
        if not self.agent_id or not isinstance(self.agent_id, str):
            raise ValueError("agent_id must be a non-empty string")
        if len(self.position) != 3:
            raise ValueError("position must be a 3D tuple (x, y, z)")
        if self.speed < 0:
            raise ValueError("speed must be non-negative")
        if not (0.0 <= self.battery_pct <= 100.0):
            raise ValueError("battery_pct must be in [0, 100]")
        if not (0.0 <= self.fuel_pct <= 100.0):
            raise ValueError("fuel_pct must be in [0, 100]")
        if self.comms_status not in {"nominal", "degraded", "lost"}:
            raise ValueError("comms_status must be one of nominal/degraded/lost")
        self.heading = float(self.heading) % 360.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert agent status to API-safe dictionary."""
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "state": self.state.value,
            "capability": self.capability.value,
            "position": list(self.position),
            "heading": self.heading,
            "speed": self.speed,
            "battery_pct": self.battery_pct,
            "fuel_pct": self.fuel_pct,
            "current_mission": self.current_mission,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "sensor_loadout": list(self.sensor_loadout),
            "weapon_loadout": list(self.weapon_loadout),
            "comms_status": self.comms_status,
        }

    def is_available(self) -> bool:
        """Availability gate for assigning time-sensitive tactical tasks."""
        return self.state in {AgentState.IDLE, AgentState.ACTIVE} and self.battery_pct > 10.0

    def distance_to(self, x: float, y: float, z: float) -> float:
        """Compute Euclidean distance to target point in mission grid."""
        return math.dist(self.position, (float(x), float(y), float(z)))


class MissionType(Enum):
    """Mission taxonomy used by autonomy planners and operators."""

    PATROL = "patrol"
    RECON = "recon"
    INTERCEPT = "intercept"
    ESCORT = "escort"
    SEARCH_AND_RESCUE = "search_and_rescue"
    STRIKE = "strike"
    HOLD_POSITION = "hold_position"
    RETURN_TO_BASE = "return_to_base"
    CUSTOM = "custom"


class MissionStatus(Enum):
    """Execution lifecycle status for tactical missions."""

    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


@dataclass
class Mission:
    """Mission definition with assignment and rules-of-engagement details."""

    mission_id: str
    mission_type: MissionType
    status: MissionStatus
    title: str
    description: str
    assigned_agents: List[str]
    waypoints: List[Tuple[float, float, float]]
    priority: int
    rules_of_engagement: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.mission_id:
            raise ValueError("mission_id is required")
        if not self.title:
            raise ValueError("title is required")
        if not self.description:
            raise ValueError("description is required")
        if not (1 <= self.priority <= 5):
            raise ValueError("priority must be between 1 and 5")
        if not self.rules_of_engagement:
            raise ValueError("rules_of_engagement is required")
        for wp in self.waypoints:
            if len(wp) != 3:
                raise ValueError("each waypoint must be a 3D tuple")

    def to_dict(self) -> Dict[str, Any]:
        """Return mission payload for APIs and audit logging."""
        return {
            "mission_id": self.mission_id,
            "mission_type": self.mission_type.value,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "assigned_agents": list(self.assigned_agents),
            "waypoints": [list(wp) for wp in self.waypoints],
            "priority": self.priority,
            "rules_of_engagement": self.rules_of_engagement,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "parameters": dict(self.parameters),
        }

    def duration_seconds(self) -> Optional[float]:
        """Mission duration for after-action review and readiness analytics."""
        if self.started_at is None:
            return None
        end_time = self.completed_at or datetime.now(timezone.utc)
        return max(0.0, (end_time - self.started_at).total_seconds())


class CommandType(Enum):
    """Command vocabulary for tactical swarm control."""

    MOVE_TO = "move_to"
    HOLD = "hold"
    ENGAGE = "engage"
    DISENGAGE = "disengage"
    CHANGE_FORMATION = "change_formation"
    SET_SPEED = "set_speed"
    CHANGE_ALTITUDE = "change_altitude"
    RTB = "rtb"
    REPLAN = "replan"
    EMERGENCY_STOP = "emergency_stop"


@dataclass
class SwarmCommand:
    """Validated command with expiry semantics for reliable C2 messaging."""

    command_id: str
    command_type: CommandType
    target_agents: List[str]
    parameters: Dict[str, Any]
    issued_by: str
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    priority: int = 3
    ttl_seconds: float = 60.0

    def __post_init__(self) -> None:
        if not self.command_id:
            raise ValueError("command_id is required")
        if not self.target_agents:
            raise ValueError("target_agents cannot be empty")
        if self.ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if self.priority < 1:
            raise ValueError("priority must be >= 1")

    def to_dict(self) -> Dict[str, Any]:
        """Dictionary form for protocol encoding and API responses."""
        return {
            "command_id": self.command_id,
            "command_type": self.command_type.value,
            "target_agents": list(self.target_agents),
            "parameters": dict(self.parameters),
            "issued_by": self.issued_by,
            "issued_at": self.issued_at.isoformat(),
            "priority": self.priority,
            "ttl_seconds": self.ttl_seconds,
        }

    def is_expired(self) -> bool:
        """Check if command exceeded tactical execution window."""
        return (datetime.now(timezone.utc) - self.issued_at).total_seconds() > self.ttl_seconds


class FormationType(Enum):
    """Common formation geometries for tactical swarm maneuver."""

    LINE = "line"
    WEDGE = "wedge"
    DIAMOND = "diamond"
    CIRCLE = "circle"
    ECHELON_LEFT = "echelon_left"
    ECHELON_RIGHT = "echelon_right"
    COLUMN = "column"
    SPREAD = "spread"
    CUSTOM = "custom"


@dataclass
class Formation:
    """Formation definition used to derive absolute station-keeping points."""

    formation_type: FormationType
    spacing_meters: float
    heading: float
    agent_positions: Dict[str, Tuple[float, float, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.spacing_meters <= 0:
            raise ValueError("spacing_meters must be positive")
        self.heading = self.heading % 360.0

    def compute_positions(
        self,
        leader_pos: Tuple[float, float, float],
        agent_ids: List[str],
    ) -> Dict[str, Tuple[float, float, float]]:
        """Compute tactical station positions anchored on leader coordinates."""
        if not agent_ids:
            return {}
        if len(leader_pos) != 3:
            raise ValueError("leader_pos must be a 3D tuple")

        heading_rad = math.radians(self.heading)
        forward = (math.cos(heading_rad), math.sin(heading_rad))
        right = (-math.sin(heading_rad), math.cos(heading_rad))
        lx, ly, lz = leader_pos

        def project(offset_forward: float, offset_right: float) -> Tuple[float, float, float]:
            ox = forward[0] * offset_forward + right[0] * offset_right
            oy = forward[1] * offset_forward + right[1] * offset_right
            return (lx + ox, ly + oy, lz)

        positions: Dict[str, Tuple[float, float, float]] = {agent_ids[0]: (lx, ly, lz)}
        if self.formation_type == FormationType.CUSTOM and self.agent_positions:
            for aid in agent_ids:
                rel = self.agent_positions.get(aid, (0.0, 0.0, 0.0))
                positions[aid] = (lx + rel[0], ly + rel[1], lz + rel[2])
            return positions

        for idx, agent_id in enumerate(agent_ids[1:], start=1):
            if self.formation_type == FormationType.LINE:
                side = -1 if idx % 2 == 0 else 1
                rank = (idx + 1) // 2
                positions[agent_id] = project(0.0, side * rank * self.spacing_meters)
            elif self.formation_type == FormationType.WEDGE:
                side = -1 if idx % 2 == 0 else 1
                rank = (idx + 1) // 2
                positions[agent_id] = project(-rank * self.spacing_meters, side * rank * self.spacing_meters)
            elif self.formation_type == FormationType.COLUMN:
                positions[agent_id] = project(-idx * self.spacing_meters, 0.0)
            elif self.formation_type == FormationType.ECHELON_LEFT:
                positions[agent_id] = project(-idx * self.spacing_meters, -idx * self.spacing_meters)
            elif self.formation_type == FormationType.ECHELON_RIGHT:
                positions[agent_id] = project(-idx * self.spacing_meters, idx * self.spacing_meters)
            elif self.formation_type == FormationType.CIRCLE:
                angle = (2.0 * math.pi * idx) / max(1, len(agent_ids) - 1)
                positions[agent_id] = (
                    lx + math.cos(angle) * self.spacing_meters,
                    ly + math.sin(angle) * self.spacing_meters,
                    lz,
                )
            elif self.formation_type == FormationType.DIAMOND:
                pattern = [
                    (-self.spacing_meters, 0.0),
                    (-2 * self.spacing_meters, self.spacing_meters),
                    (-2 * self.spacing_meters, -self.spacing_meters),
                    (-3 * self.spacing_meters, 0.0),
                ]
                rel = pattern[(idx - 1) % len(pattern)]
                positions[agent_id] = project(rel[0], rel[1])
            else:  # SPREAD and fallback
                side = -1 if idx % 2 == 0 else 1
                positions[agent_id] = project(-idx * self.spacing_meters, side * idx * self.spacing_meters)
        return positions


class DecisionType(Enum):
    """Decision categories for autonomous tactical behavior."""

    ENGAGE = "engage"
    AVOID = "avoid"
    REPLAN = "replan"
    ESCALATE = "escalate"
    HOLD = "hold"
    PURSUE = "pursue"
    RETREAT = "retreat"
    DELEGATE = "delegate"
    STRIKE = "strike"
    BAYESIAN_INFERENCE = "bayesian_inference"
    PARETO_SELECTION = "pareto_selection"
    POMDP_ACTION = "pomdp_action"


@dataclass
class AutonomyDecision:
    """Auditable autonomy decision record for XAI and legal traceability."""

    decision_id: str
    timestamp: datetime
    decision_type: DecisionType
    agent_id: str
    mission_id: Optional[str]
    context: Dict[str, Any]
    action_taken: Dict[str, Any]
    alternatives_considered: List[Dict[str, Any]]
    confidence: float
    reasoning: str
    llm_consulted: bool
    requires_human_review: bool
    risk_score: float

    def __post_init__(self) -> None:
        if not self.decision_id:
            raise ValueError("decision_id is required")
        if not self.agent_id:
            raise ValueError("agent_id is required")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be in [0, 1]")
        if not (0.0 <= self.risk_score <= 1.0):
            raise ValueError("risk_score must be in [0, 1]")
        if not self.reasoning:
            raise ValueError("reasoning is required")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize decision for API responses and disk logging."""
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp.isoformat(),
            "decision_type": self.decision_type.value,
            "agent_id": self.agent_id,
            "mission_id": self.mission_id,
            "context": dict(self.context),
            "action_taken": dict(self.action_taken),
            "alternatives_considered": list(self.alternatives_considered),
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "llm_consulted": self.llm_consulted,
            "requires_human_review": self.requires_human_review,
            "risk_score": self.risk_score,
        }

    def to_audit_entry(self) -> Dict[str, Any]:
        """Return concise audit entry for command authority and accountability."""
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp.isoformat(),
            "decision_type": self.decision_type.value,
            "agent_id": self.agent_id,
            "mission_id": self.mission_id,
            "action_taken": self.action_taken,
            "confidence": self.confidence,
            "risk_score": self.risk_score,
            "requires_human_review": self.requires_human_review,
            "llm_consulted": self.llm_consulted,
            "reasoning": self.reasoning,
        }
