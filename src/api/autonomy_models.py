"""Pydantic models for Phase 6 autonomy and swarm API endpoints.

These schemas validate command-and-control payloads so autonomy interfaces stay
safe, auditable, and consistent in tactical edge deployments.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from src.autonomy.models import (
    AgentCapability,
    AgentRole,
    AgentState,
    CommandType,
    DecisionType,
    FormationType,
    MissionStatus,
    MissionType,
)


class RegisterAgentRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=128)
    role: AgentRole
    state: AgentState = AgentState.IDLE
    capability: AgentCapability
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    heading: float = Field(default=0.0, ge=0.0, le=360.0)
    speed: float = Field(default=0.0, ge=0.0, le=200.0)
    battery_pct: float = Field(default=100.0, ge=0.0, le=100.0)
    fuel_pct: float = Field(default=100.0, ge=0.0, le=100.0)
    current_mission: Optional[str] = None
    sensor_loadout: List[str] = Field(default_factory=list)
    weapon_loadout: List[str] = Field(default_factory=list)
    comms_status: Literal["nominal", "degraded", "lost"] = "nominal"


class AgentResponse(BaseModel):
    agent_id: str
    role: AgentRole
    state: AgentState
    capability: AgentCapability
    position: tuple[float, float, float]
    heading: float
    speed: float
    battery_pct: float
    fuel_pct: float
    current_mission: Optional[str]
    last_heartbeat: datetime
    sensor_loadout: List[str]
    weapon_loadout: List[str]
    comms_status: str


class InlineMissionPayload(BaseModel):
    mission_id: str = Field(..., min_length=1, max_length=128)
    mission_type: MissionType
    title: str = Field(..., min_length=1, max_length=256)
    description: str = Field(..., min_length=1, max_length=2000)
    assigned_agents: List[str] = Field(default_factory=list)
    waypoints: List[tuple[float, float, float]] = Field(default_factory=list)
    priority: int = Field(default=3, ge=1, le=5)
    rules_of_engagement: str = Field(default="weapons_hold", min_length=1, max_length=64)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class StartMissionRequest(BaseModel):
    mission: Optional[InlineMissionPayload] = None
    yaml_path: Optional[str] = Field(default=None, min_length=1)

    @field_validator("yaml_path")
    @classmethod
    def _safe_yaml_path(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if ".." in value:
            raise ValueError("yaml_path cannot contain '..'")
        return value


class MissionResponse(BaseModel):
    mission_id: str
    mission_type: MissionType
    status: MissionStatus
    title: str
    description: str
    assigned_agents: List[str]
    waypoints: List[tuple[float, float, float]]
    priority: int
    rules_of_engagement: str
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    parameters: Dict[str, Any]


class SwarmCommandRequest(BaseModel):
    command_type: CommandType
    target_agents: List[str] = Field(default_factory=lambda: ["all"])
    parameters: Dict[str, Any] = Field(default_factory=dict)
    issued_by: str = Field(default="operator", min_length=1, max_length=64)
    priority: int = Field(default=3, ge=1, le=10)
    ttl_seconds: float = Field(default=60.0, gt=0.0, le=3600.0)


class NLCommandRequest(BaseModel):
    natural_language: str = Field(..., min_length=1, max_length=2048)
    language: Literal["en", "ar"] = "en"


class FormationRequest(BaseModel):
    formation_type: FormationType
    spacing: float = Field(default=20.0, gt=0.0, le=200.0)


class TrainRLRequest(BaseModel):
    env_name: str = Field(default="MilitaryEnvironment", min_length=1, max_length=128)
    algorithm: str = Field(default="PPO", min_length=1, max_length=32)
    n_steps: int = Field(default=10000, ge=1, le=2_000_000)


class DecisionQueryParams(BaseModel):
    agent_id: Optional[str] = None
    decision_type: Optional[DecisionType] = None
    mission_id: Optional[str] = None
    requires_review: Optional[bool] = None
    limit: int = Field(default=50, ge=1, le=1000)


class DecisionResponse(BaseModel):
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


class ExplanationResponse(BaseModel):
    decision_id: str
    summary: str
    factors: List[Dict[str, Any]]
    alternatives: List[Dict[str, Any]]
    risk_assessment: Dict[str, Any]
    recommendation: str
    llm_exchange: Optional[Dict[str, Any]] = None


class AutonomyStatusResponse(BaseModel):
    status: str
    rl: Dict[str, Any]
    swarm: Dict[str, Any]
    xai: Dict[str, Any]
    missions: int
    timestamp: str


class SwarmStatusResponse(BaseModel):
    total_agents: int
    by_state: Dict[str, int]
    by_role: Dict[str, int]
    active_missions: List[str]
    current_formation: Optional[Dict[str, Any]]
    last_command: Optional[Dict[str, Any]]
    queued_commands: int
