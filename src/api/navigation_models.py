"""Pydantic API models for Phase 8 navigation and edge inference endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, model_validator


class PoseResponse(BaseModel):
    position: Tuple[float, float, float]
    orientation: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    angular_velocity: Tuple[float, float, float]
    timestamp: str
    confidence: float
    source: str
    covariance: Optional[List[List[float]]] = None


class GPSStatusResponse(BaseModel):
    quality: str
    satellites_visible: int
    hdop: float
    fix_type: str
    last_fix_time: Optional[str] = None
    position: Optional[Tuple[float, float, float]] = None


class NavStateResponse(BaseModel):
    pose: PoseResponse
    gps_status: GPSStatusResponse
    localization_mode: str
    active_sources: List[str]
    drift_estimate_meters: float
    last_update: str


class PlanPathRequest(BaseModel):
    start: Tuple[float, float, float]
    goal: Tuple[float, float, float]
    obstacles: List[Dict[str, Any]] = Field(default_factory=list)
    planner_type: Optional[str] = None
    platform_type: Optional[str] = None


class WaypointInput(BaseModel):
    position: Tuple[float, float, float]
    radius: float = Field(default=2.0, ge=0.0)
    speed: Optional[float] = Field(default=None, ge=0.0)
    loiter_seconds: float = Field(default=0.0, ge=0.0)
    heading: Optional[float] = None


class PlanWaypointsRequest(BaseModel):
    waypoints: List[WaypointInput] = Field(min_length=2)
    platform_type: str = "quadrotor"


class PathResponse(BaseModel):
    path_id: str
    planner_type: str
    status: str
    waypoints: List[Tuple[float, float, float]]
    total_distance: float
    estimated_time: float
    obstacles_avoided: int
    computation_time_ms: float
    created_at: str


class TrajectoryPointResponse(BaseModel):
    time: float
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    acceleration: Tuple[float, float, float]
    yaw: float
    yaw_rate: float


class TrajectoryResponse(BaseModel):
    trajectory_id: str
    path_id: str
    points: List[TrajectoryPointResponse]
    platform_type: str
    duration: float
    max_velocity: float
    max_acceleration: float
    feasible: bool


class CollisionCheckResponse(BaseModel):
    safe: bool
    collisions: List[Dict[str, Any]]
    nearest_miss_meters: float
    time_to_collision_seconds: Optional[float] = None


class ReplanRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=128)
    new_obstacles: List[Dict[str, Any]] = Field(default_factory=list)


class UpdateNavRequest(BaseModel):
    plan_id: str = Field(min_length=1, max_length=128)
    current_pose: PoseResponse


class OptimizeTrajectoryRequest(BaseModel):
    path: PathResponse
    platform_type: Optional[str] = None


class OptimizeModelRequest(BaseModel):
    model_path: str = Field(min_length=1, max_length=4096)
    precision: str = "fp16"
    input_shape: Optional[List[int]] = None


class EdgeModelResponse(BaseModel):
    model_id: str
    name: str
    framework: str
    precision: str
    file_path: str
    file_size_bytes: int
    input_shape: List[int]
    output_shape: List[int]
    avg_latency_ms: float
    memory_usage_mb: float
    loaded: bool


class PredictRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=128)
    input_data: Any


class InferenceResultResponse(BaseModel):
    model_id: str
    output: Any
    latency_ms: float
    timestamp: str


class JetsonStatsResponse(BaseModel):
    gpu_utilization_pct: float
    gpu_memory_used_mb: float
    gpu_memory_total_mb: float
    cpu_utilization_pct: float
    ram_used_mb: float
    ram_total_mb: float
    temperature_gpu_c: float
    temperature_cpu_c: float
    power_draw_watts: float
    power_budget_watts: float
    cuda_version: Optional[str] = None
    tensorrt_available: bool
    onnx_available: bool
    simulated: Optional[bool] = None


class NavigationStatusResponse(BaseModel):
    localization: Dict[str, Any]
    planning: Dict[str, Any]
    edge_inference: Dict[str, Any]
    jetson: Dict[str, Any]
    active_plans: List[Dict[str, Any]]


class ResetLocalizationRequest(BaseModel):
    position: Tuple[float, float, float]


class PlanResultResponse(BaseModel):
    path: PathResponse
    trajectory: TrajectoryResponse
    collision_check: CollisionCheckResponse
    plan_id: str


class WaypointMissionResponse(BaseModel):
    nav_plan_id: str


class NavigationUpdateResponse(BaseModel):
    target_position: Tuple[float, float, float]
    target_velocity: Tuple[float, float, float]
    target_yaw: float
    waypoint_index: int
    segment_progress: float
    status: str


class GenericStatusResponse(BaseModel):
    status: str
    detail: Optional[str] = None


class PlanQueryResponse(BaseModel):
    plan_id: str
    path: Optional[PathResponse] = None
    trajectory: Optional[TrajectoryResponse] = None
    collision_check: Optional[CollisionCheckResponse] = None


class PredictBatchRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=128)
    batch_data: List[Any]


class PoseHistoryResponse(BaseModel):
    poses: List[PoseResponse]
    total: int

    @model_validator(mode="after")
    def _validate_total(self) -> "PoseHistoryResponse":
        if self.total != len(self.poses):
            self.total = len(self.poses)
        return self
