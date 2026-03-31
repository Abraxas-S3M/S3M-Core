"""Pydantic response and request models for Layer 06 dashboard."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DashboardOverviewResponse(BaseModel):
    timestamp: str
    llm: Dict[str, Any]
    threats: Dict[str, Any]
    autonomy: Dict[str, Any]
    simulation: Dict[str, Any]
    navigation: Dict[str, Any]
    system: Dict[str, Any]


class COPDataResponse(BaseModel):
    agents: List[Dict[str, Any]] = Field(default_factory=list)
    threats: List[Dict[str, Any]] = Field(default_factory=list)
    tracks: List[Dict[str, Any]] = Field(default_factory=list)
    paths: List[Dict[str, Any]] = Field(default_factory=list)
    formations: Dict[str, Any] = Field(default_factory=dict)
    terrain: Dict[str, Any] = Field(default_factory=dict)
    bounds: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""


class EngineStatusItem(BaseModel):
    name: str
    provider: str
    status: str
    domain: str
    params: str
    quantization: str


class EngineStatusResponse(BaseModel):
    engines: List[EngineStatusItem] = Field(default_factory=list)
    total: int = 0


class LLMMetricsResponse(BaseModel):
    total_requests: int = 0
    uptime_seconds: int = 0
    engines_loaded: int = 0
    avg_latency_ms: float = 0.0
    requests_per_minute: float = 0.0
    engines_simulated: int = 0


class AuditEntryResponse(BaseModel):
    id: str
    timestamp: str
    action: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ThreatFeedItem(BaseModel):
    id: str
    timestamp: str
    level: str
    category: str
    source: str
    title: str
    description: str
    confidence: float
    position: Any = None


class ThreatFeedResponse(BaseModel):
    events: List[ThreatFeedItem] = Field(default_factory=list)
    total: int = 0


class ThreatStatsResponse(BaseModel):
    total_events: int = 0
    critical: int = 0
    high: int = 0
    active_sensors: int = 0
    by_level: Dict[str, int] = Field(default_factory=dict)
    by_category: Dict[str, int] = Field(default_factory=dict)
    by_source: Dict[str, int] = Field(default_factory=dict)
    timeline: List[Dict[str, Any]] = Field(default_factory=list)


class ThreatHeatmapItem(BaseModel):
    position: Any = None
    intensity: float
    category: str


class ThreatHeatmapResponse(BaseModel):
    items: List[ThreatHeatmapItem] = Field(default_factory=list)
    total: int = 0


class AgentRosterItem(BaseModel):
    id: str
    role: str
    state: str
    position: Any = None
    battery: float
    capability: str
    last_heartbeat: str
    time_since_heartbeat: float
    mission_name: str
    formation_position: str


class AgentRosterResponse(BaseModel):
    agents: List[AgentRosterItem] = Field(default_factory=list)
    total: int = 0


class MissionItem(BaseModel):
    id: str
    type: str
    status: str
    assigned_agents: List[str] = Field(default_factory=list)
    progress_pct: float
    duration: float
    waypoints_completed: int


class MissionListResponse(BaseModel):
    missions: List[MissionItem] = Field(default_factory=list)
    total: int = 0


class DecisionFeedItem(BaseModel):
    id: str
    type: str
    agent_id: str
    confidence: float
    risk_score: float
    requires_review: bool
    reasoning_snippet: str
    timestamp: str
    status: str
    context: str = ""


class DecisionFeedResponse(BaseModel):
    decisions: List[DecisionFeedItem] = Field(default_factory=list)
    total: int = 0


class ReviewQueueItem(BaseModel):
    id: str
    type: str
    agent_id: str
    confidence: float
    risk_score: float
    requires_review: bool
    reasoning_snippet: str
    timestamp: str
    status: str
    context: str = ""
    xai_explanation: Dict[str, Any] = Field(default_factory=dict)


class ReviewQueueResponse(BaseModel):
    items: List[ReviewQueueItem] = Field(default_factory=list)
    total: int = 0


class DecisionExplanationResponse(BaseModel):
    decision_id: str
    summary: str
    factors: List[Any] = Field(default_factory=list)
    alternatives: List[Any] = Field(default_factory=list)
    risk_assessment: Dict[str, Any] = Field(default_factory=dict)


class NLCommandRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1024)
    language: str = Field(default="en", pattern="^(en|ar)$")


class NLCommandResponse(BaseModel):
    status: str
    parsed_command: Dict[str, Any] = Field(default_factory=dict)
    detail: Optional[str] = None


class SystemHealthResponse(BaseModel):
    overall_status: str
    layers: Dict[str, Any] = Field(default_factory=dict)
    uptime_seconds: int = 0
    total_api_endpoints: int = 0
    api_health: Dict[str, int] = Field(default_factory=dict)
    timestamp: Optional[str] = None


class JetsonStatsResponse(BaseModel):
    gpu_util_pct: float = 0.0
    memory_pct: float = 0.0
    temperature_c: float = 0.0
    power_w: float = 0.0
    cuda_version: str = "unknown"
    status: str = "simulated"


class EdgeModelItem(BaseModel):
    name: str
    precision: str
    latency_ms: float
    memory_mb: float
    status: str


class EdgeModelListResponse(BaseModel):
    models: List[EdgeModelItem] = Field(default_factory=list)
    total: int = 0


class AlertItemResponse(BaseModel):
    alert_id: str
    timestamp: str
    level: str
    source_layer: str
    title: str
    message: str
    action_url: str


class AlertListResponse(BaseModel):
    alerts: List[AlertItemResponse] = Field(default_factory=list)
    total: int = 0


class AlertCountResponse(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    total: int = 0

