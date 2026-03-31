"""Pydantic models for S3M Phase 7 simulation and wargaming API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, model_validator


class ConnectSimulatorRequest(BaseModel):
    simulator_name: str = Field(..., min_length=1, max_length=64)
    host: str = Field(default="localhost", min_length=1, max_length=256)
    port: int = Field(default=0, ge=0, le=65535)
    world_file: Optional[str] = Field(default=None, max_length=4096)
    headless: bool = True
    extra_params: Dict[str, Any] = Field(default_factory=dict)


class SimEntityResponse(BaseModel):
    entity_id: str
    entity_type: str
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    heading: float
    health: float
    active: bool
    metadata: Dict[str, Any]


class SimulationStateResponse(BaseModel):
    timestamp: str
    sim_time_seconds: float
    entities: List[SimEntityResponse]
    terrain: Dict[str, Any]
    weather: Dict[str, Any]
    active_events: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class LoadScenarioRequest(BaseModel):
    yaml_path: Optional[str] = Field(default=None, max_length=4096)
    inline: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _validate_source(self) -> "LoadScenarioRequest":
        if not self.yaml_path and not self.inline:
            raise ValueError("either yaml_path or inline scenario data is required")
        return self


class RunScenarioRequest(BaseModel):
    max_ticks: int = Field(default=6000, ge=1, le=200000)
    tick_dt: float = Field(default=0.1, gt=0.0, le=60.0)
    opfor_strategy: str = Field(default="adaptive", pattern="^(static|scripted|random|adaptive)$")
    record_replay: bool = True


class ScenarioStatusResponse(BaseModel):
    scenario_id: Optional[str] = None
    status: str
    running: bool
    tick: int
    sim_time_seconds: float
    entities_alive: int
    friendlies_alive: int
    enemies_alive: int


class AARReportResponse(BaseModel):
    aar_id: str
    scenario_id: str
    timestamp: str
    duration_seconds: float
    outcome: str
    friendly_losses: int
    enemy_losses: int
    objectives_met: List[str]
    objectives_failed: List[str]
    timeline: List[Dict[str, Any]]
    llm_analysis: Optional[str] = None
    lessons_learned: List[str]
    statistics: Dict[str, Any]


class GenerateOpForRequest(BaseModel):
    strategy: str = Field(default="adaptive", pattern="^(static|scripted|random|adaptive)$")
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard|nightmare)$")
    current_state: Optional[Dict[str, Any]] = None


class GenerateTabularRequest(BaseModel):
    data_type: str = Field(..., pattern="^(network|sensor|logistics)$")
    n_records: int = Field(default=1000, ge=1, le=2_000_000)
    params: Dict[str, Any] = Field(default_factory=dict)


class GenerateTrajectoryRequest(BaseModel):
    trajectory_type: str = Field(default="swarm")
    n_agents: int = Field(default=4, ge=1, le=500)
    duration: float = Field(default=120.0, gt=0.0, le=86_400.0)
    params: Dict[str, Any] = Field(default_factory=dict)


class GenerateScenarioDataRequest(BaseModel):
    scenario_type: str = Field(default="ambush")
    n_events: int = Field(default=50, ge=1, le=100_000)
    params: Dict[str, Any] = Field(default_factory=dict)


class SyntheticGenerateRequest(BaseModel):
    type: str = Field(..., pattern="^(network|sensor|logistics|trajectory|scenario)$")
    n_records: int = Field(default=1000, ge=1, le=2_000_000)
    params: Dict[str, Any] = Field(default_factory=dict)


class SyntheticDatasetResponse(BaseModel):
    dataset_id: str
    name: str
    description: str
    generator: str
    created_at: str
    record_count: int
    file_path: str
    file_size_bytes: int
    checksum_sha256: str
    dataset_schema: Dict[str, Any] = Field(alias="schema")
    generation_params: Dict[str, Any]
    license: str


class ReplayArtifactResponse(BaseModel):
    replay_id: str
    scenario_id: Optional[str] = None
    simulator: str
    created_at: str
    duration_seconds: float
    tick_count: int
    filepath: str
    file_size_bytes: int
    metadata: Dict[str, Any]


class SimulationStatusResponse(BaseModel):
    status: str
    active_adapter: str
    adapters: Dict[str, Dict[str, Any]]
    loaded_scenario_id: Optional[str] = None
    dataset_count: int
    replay_count: int
