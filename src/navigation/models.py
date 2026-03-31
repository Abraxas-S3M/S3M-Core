"""Navigation and edge inference data models for S3M Layer 05."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import degrees, sqrt
from typing import Any, Dict, List, Optional, Tuple


def _ensure_tuple3(name: str, value: Tuple[float, float, float]) -> Tuple[float, float, float]:
    if not isinstance(value, tuple) or len(value) != 3:
        raise ValueError(f"{name} must be a tuple of 3 numeric values")
    if not all(isinstance(v, (int, float)) for v in value):
        raise ValueError(f"{name} must contain numeric values")
    return (float(value[0]), float(value[1]), float(value[2]))


def _ensure_non_negative(name: str, value: float) -> float:
    if not isinstance(value, (int, float)) or float(value) < 0.0:
        raise ValueError(f"{name} must be a non-negative number")
    return float(value)


class GPSQuality(str, Enum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    DENIED = "DENIED"
    SPOOFED = "SPOOFED"
    UNKNOWN = "UNKNOWN"


@dataclass
class GPSStatus:
    quality: GPSQuality
    satellites_visible: int
    hdop: float
    fix_type: str
    last_fix_time: Optional[datetime] = None
    position: Optional[Tuple[float, float, float]] = None

    def __post_init__(self) -> None:
        if not isinstance(self.quality, GPSQuality):
            self.quality = GPSQuality(str(self.quality))
        if not isinstance(self.satellites_visible, int) or self.satellites_visible < 0:
            raise ValueError("satellites_visible must be a non-negative integer")
        self.hdop = _ensure_non_negative("hdop", self.hdop)
        if not isinstance(self.fix_type, str) or not self.fix_type.strip():
            raise ValueError("fix_type must be a non-empty string")
        self.fix_type = self.fix_type.strip().lower()
        if self.position is not None:
            self.position = _ensure_tuple3("position", self.position)
        if self.last_fix_time is not None and not isinstance(self.last_fix_time, datetime):
            raise ValueError("last_fix_time must be datetime or None")

    def is_usable(self) -> bool:
        return self.quality in {GPSQuality.EXCELLENT, GPSQuality.GOOD}

    def is_denied(self) -> bool:
        return self.quality in {GPSQuality.DENIED, GPSQuality.SPOOFED}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quality": self.quality.value,
            "satellites_visible": self.satellites_visible,
            "hdop": self.hdop,
            "fix_type": self.fix_type,
            "last_fix_time": self.last_fix_time.isoformat() if self.last_fix_time else None,
            "position": self.position,
        }


@dataclass
class Pose:
    position: Tuple[float, float, float]
    orientation: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    angular_velocity: Tuple[float, float, float]
    timestamp: datetime
    confidence: float
    source: str
    covariance: Optional[List[List[float]]] = None

    def __post_init__(self) -> None:
        self.position = _ensure_tuple3("position", self.position)
        self.orientation = _ensure_tuple3("orientation", self.orientation)
        self.velocity = _ensure_tuple3("velocity", self.velocity)
        self.angular_velocity = _ensure_tuple3("angular_velocity", self.angular_velocity)
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be datetime")
        if not isinstance(self.confidence, (int, float)) or not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("confidence must be in [0, 1]")
        self.confidence = float(self.confidence)
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty string")
        self.source = self.source.strip()
        if self.covariance is not None:
            if not isinstance(self.covariance, list) or len(self.covariance) != 6:
                raise ValueError("covariance must be a 6x6 list when provided")
            for row in self.covariance:
                if not isinstance(row, list) or len(row) != 6:
                    raise ValueError("covariance must be a 6x6 list when provided")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": self.position,
            "orientation": self.orientation,
            "velocity": self.velocity,
            "angular_velocity": self.angular_velocity,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "source": self.source,
            "covariance": self.covariance,
        }

    def distance_to(self, other_pose: "Pose") -> float:
        if not isinstance(other_pose, Pose):
            raise ValueError("other_pose must be a Pose")
        dx = self.position[0] - other_pose.position[0]
        dy = self.position[1] - other_pose.position[1]
        dz = self.position[2] - other_pose.position[2]
        return sqrt(dx * dx + dy * dy + dz * dz)

    def heading_deg(self) -> float:
        return (degrees(self.orientation[2]) + 360.0) % 360.0


@dataclass
class NavState:
    pose: Pose
    gps_status: GPSStatus
    localization_mode: str
    active_sources: List[str]
    drift_estimate_meters: float
    last_update: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.pose, Pose):
            raise ValueError("pose must be a Pose")
        if not isinstance(self.gps_status, GPSStatus):
            raise ValueError("gps_status must be a GPSStatus")
        if not isinstance(self.localization_mode, str) or not self.localization_mode.strip():
            raise ValueError("localization_mode must be a non-empty string")
        if not isinstance(self.active_sources, list) or any(not isinstance(s, str) for s in self.active_sources):
            raise ValueError("active_sources must be a list of strings")
        self.drift_estimate_meters = _ensure_non_negative("drift_estimate_meters", self.drift_estimate_meters)
        if not isinstance(self.last_update, datetime):
            raise ValueError("last_update must be datetime")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pose": self.pose.to_dict(),
            "gps_status": self.gps_status.to_dict(),
            "localization_mode": self.localization_mode,
            "active_sources": list(self.active_sources),
            "drift_estimate_meters": self.drift_estimate_meters,
            "last_update": self.last_update.isoformat(),
        }


class PlatformType(str, Enum):
    QUADROTOR = "quadrotor"
    FIXED_WING = "fixed_wing"
    GROUND_WHEELED = "ground_wheeled"
    GROUND_TRACKED = "ground_tracked"
    MARITIME_SURFACE = "maritime_surface"
    MARITIME_SUB = "maritime_sub"

    @classmethod
    def from_value(cls, value: str | "PlatformType") -> "PlatformType":
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Invalid platform type: {value}")
        normalized = value.strip().lower()
        for item in cls:
            if item.value == normalized:
                return item
        raise ValueError(f"Invalid platform type: {value}")


@dataclass
class PlatformConstraints:
    platform_type: PlatformType
    max_velocity: float
    max_acceleration: float
    max_jerk: float
    max_yaw_rate: float
    min_turn_radius: float
    max_altitude: float
    min_altitude: float
    max_climb_rate: float
    max_descent_rate: float
    collision_radius: float

    def __post_init__(self) -> None:
        self.platform_type = PlatformType.from_value(self.platform_type)
        self.max_velocity = _ensure_non_negative("max_velocity", self.max_velocity)
        self.max_acceleration = _ensure_non_negative("max_acceleration", self.max_acceleration)
        self.max_jerk = _ensure_non_negative("max_jerk", self.max_jerk)
        self.max_yaw_rate = _ensure_non_negative("max_yaw_rate", self.max_yaw_rate)
        self.min_turn_radius = _ensure_non_negative("min_turn_radius", self.min_turn_radius)
        self.max_altitude = float(self.max_altitude)
        self.min_altitude = float(self.min_altitude)
        if self.max_altitude < self.min_altitude:
            raise ValueError("max_altitude must be greater than or equal to min_altitude")
        self.max_climb_rate = _ensure_non_negative("max_climb_rate", self.max_climb_rate)
        self.max_descent_rate = _ensure_non_negative("max_descent_rate", self.max_descent_rate)
        self.collision_radius = _ensure_non_negative("collision_radius", self.collision_radius)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform_type": self.platform_type.value,
            "max_velocity": self.max_velocity,
            "max_acceleration": self.max_acceleration,
            "max_jerk": self.max_jerk,
            "max_yaw_rate": self.max_yaw_rate,
            "min_turn_radius": self.min_turn_radius,
            "max_altitude": self.max_altitude,
            "min_altitude": self.min_altitude,
            "max_climb_rate": self.max_climb_rate,
            "max_descent_rate": self.max_descent_rate,
            "collision_radius": self.collision_radius,
        }


class PlannerType(str, Enum):
    RRT_STAR = "rrt_star"
    A_STAR = "a_star"
    POTENTIAL_FIELD = "potential_field"
    MPC = "mpc"
    STRAIGHT_LINE = "straight_line"

    @classmethod
    def from_value(cls, value: str | "PlannerType") -> "PlannerType":
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Invalid planner type: {value}")
        normalized = value.strip().lower()
        for item in cls:
            if item.value == normalized:
                return item
        raise ValueError(f"Invalid planner type: {value}")


class PathStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    REPLANNING = "replanning"
    FAILED = "failed"


@dataclass
class Waypoint:
    position: Tuple[float, float, float]
    radius: float
    speed: Optional[float] = None
    loiter_seconds: float = 0.0
    heading: Optional[float] = None

    def __post_init__(self) -> None:
        self.position = _ensure_tuple3("position", self.position)
        self.radius = _ensure_non_negative("radius", self.radius)
        if self.speed is not None:
            self.speed = _ensure_non_negative("speed", self.speed)
        self.loiter_seconds = _ensure_non_negative("loiter_seconds", self.loiter_seconds)
        if self.heading is not None and not isinstance(self.heading, (int, float)):
            raise ValueError("heading must be numeric degrees or None")
        if self.heading is not None:
            self.heading = float(self.heading)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": self.position,
            "radius": self.radius,
            "speed": self.speed,
            "loiter_seconds": self.loiter_seconds,
            "heading": self.heading,
        }

    def is_reached(
        self,
        current_position: Tuple[float, float, float],
        tolerance: Optional[float] = None,
    ) -> bool:
        current_position = _ensure_tuple3("current_position", current_position)
        threshold = self.radius if tolerance is None else _ensure_non_negative("tolerance", tolerance)
        dx = current_position[0] - self.position[0]
        dy = current_position[1] - self.position[1]
        dz = current_position[2] - self.position[2]
        return (dx * dx + dy * dy + dz * dz) ** 0.5 <= threshold


@dataclass
class Path:
    path_id: str
    planner_type: PlannerType
    status: PathStatus
    waypoints: List[Tuple[float, float, float]]
    total_distance: float
    estimated_time: float
    obstacles_avoided: int
    computation_time_ms: float
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.path_id, str) or not self.path_id.strip():
            raise ValueError("path_id must be a non-empty string")
        self.planner_type = PlannerType.from_value(self.planner_type)
        if not isinstance(self.status, PathStatus):
            self.status = PathStatus(str(self.status))
        if not isinstance(self.waypoints, list) or len(self.waypoints) < 2:
            raise ValueError("waypoints must contain at least start and goal")
        self.waypoints = [_ensure_tuple3("waypoint", wp) for wp in self.waypoints]
        self.total_distance = _ensure_non_negative("total_distance", self.total_distance)
        self.estimated_time = _ensure_non_negative("estimated_time", self.estimated_time)
        if not isinstance(self.obstacles_avoided, int) or self.obstacles_avoided < 0:
            raise ValueError("obstacles_avoided must be a non-negative integer")
        self.computation_time_ms = _ensure_non_negative("computation_time_ms", self.computation_time_ms)
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be datetime")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_id": self.path_id,
            "planner_type": self.planner_type.value,
            "status": self.status.value,
            "waypoints": self.waypoints,
            "total_distance": self.total_distance,
            "estimated_time": self.estimated_time,
            "obstacles_avoided": self.obstacles_avoided,
            "computation_time_ms": self.computation_time_ms,
            "created_at": self.created_at.isoformat(),
        }

    def segment_count(self) -> int:
        return max(0, len(self.waypoints) - 1)


@dataclass
class TrajectoryPoint:
    time: float
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float]
    acceleration: Tuple[float, float, float]
    yaw: float
    yaw_rate: float

    def __post_init__(self) -> None:
        self.time = _ensure_non_negative("time", self.time)
        self.position = _ensure_tuple3("position", self.position)
        self.velocity = _ensure_tuple3("velocity", self.velocity)
        self.acceleration = _ensure_tuple3("acceleration", self.acceleration)
        if not isinstance(self.yaw, (int, float)):
            raise ValueError("yaw must be numeric")
        if not isinstance(self.yaw_rate, (int, float)):
            raise ValueError("yaw_rate must be numeric")
        self.yaw = float(self.yaw)
        self.yaw_rate = float(self.yaw_rate)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "time": self.time,
            "position": self.position,
            "velocity": self.velocity,
            "acceleration": self.acceleration,
            "yaw": self.yaw,
            "yaw_rate": self.yaw_rate,
        }


@dataclass
class Trajectory:
    trajectory_id: str
    path_id: str
    points: List[TrajectoryPoint]
    platform_type: PlatformType
    duration: float
    max_velocity: float
    max_acceleration: float
    feasible: bool

    def __post_init__(self) -> None:
        if not isinstance(self.trajectory_id, str) or not self.trajectory_id.strip():
            raise ValueError("trajectory_id must be a non-empty string")
        if not isinstance(self.path_id, str) or not self.path_id.strip():
            raise ValueError("path_id must be a non-empty string")
        if not isinstance(self.points, list) or not self.points:
            raise ValueError("points must be a non-empty list")
        for point in self.points:
            if not isinstance(point, TrajectoryPoint):
                raise ValueError("points must contain TrajectoryPoint entries")
        self.platform_type = PlatformType.from_value(self.platform_type)
        self.duration = _ensure_non_negative("duration", self.duration)
        self.max_velocity = _ensure_non_negative("max_velocity", self.max_velocity)
        self.max_acceleration = _ensure_non_negative("max_acceleration", self.max_acceleration)
        if not isinstance(self.feasible, bool):
            raise ValueError("feasible must be bool")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trajectory_id": self.trajectory_id,
            "path_id": self.path_id,
            "points": [point.to_dict() for point in self.points],
            "platform_type": self.platform_type.value,
            "duration": self.duration,
            "max_velocity": self.max_velocity,
            "max_acceleration": self.max_acceleration,
            "feasible": self.feasible,
        }

    def sample_at(self, time_value: float) -> TrajectoryPoint:
        time_value = _ensure_non_negative("time", time_value)
        if time_value <= self.points[0].time:
            return self.points[0]
        if time_value >= self.points[-1].time:
            return self.points[-1]
        for idx in range(len(self.points) - 1):
            p0 = self.points[idx]
            p1 = self.points[idx + 1]
            if p0.time <= time_value <= p1.time:
                dt = p1.time - p0.time
                alpha = 0.0 if dt <= 0 else (time_value - p0.time) / dt
                interp = lambda a, b: float(a + (b - a) * alpha)
                return TrajectoryPoint(
                    time=time_value,
                    position=(
                        interp(p0.position[0], p1.position[0]),
                        interp(p0.position[1], p1.position[1]),
                        interp(p0.position[2], p1.position[2]),
                    ),
                    velocity=(
                        interp(p0.velocity[0], p1.velocity[0]),
                        interp(p0.velocity[1], p1.velocity[1]),
                        interp(p0.velocity[2], p1.velocity[2]),
                    ),
                    acceleration=(
                        interp(p0.acceleration[0], p1.acceleration[0]),
                        interp(p0.acceleration[1], p1.acceleration[1]),
                        interp(p0.acceleration[2], p1.acceleration[2]),
                    ),
                    yaw=interp(p0.yaw, p1.yaw),
                    yaw_rate=interp(p0.yaw_rate, p1.yaw_rate),
                )
        return self.points[-1]

    def get_position_at(self, time_value: float) -> Tuple[float, float, float]:
        return self.sample_at(time_value).position


class ModelPrecision(str, Enum):
    FP32 = "fp32"
    FP16 = "fp16"
    INT8 = "int8"
    INT4 = "int4"

    @classmethod
    def from_value(cls, value: str | "ModelPrecision") -> "ModelPrecision":
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Invalid precision: {value}")
        normalized = value.strip().lower()
        for item in cls:
            if item.value == normalized:
                return item
        raise ValueError(f"Invalid precision: {value}")


@dataclass
class EdgeModel:
    model_id: str
    name: str
    framework: str
    precision: ModelPrecision
    file_path: str
    file_size_bytes: int
    input_shape: List[int]
    output_shape: List[int]
    avg_latency_ms: float
    memory_usage_mb: float
    loaded: bool

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be non-empty string")
        if not isinstance(self.framework, str) or not self.framework.strip():
            raise ValueError("framework must be non-empty string")
        self.precision = ModelPrecision.from_value(self.precision)
        if not isinstance(self.file_path, str) or not self.file_path.strip():
            raise ValueError("file_path must be non-empty string")
        if not isinstance(self.file_size_bytes, int) or self.file_size_bytes < 0:
            raise ValueError("file_size_bytes must be non-negative int")
        if not isinstance(self.input_shape, list) or any(not isinstance(v, int) for v in self.input_shape):
            raise ValueError("input_shape must be a list of ints")
        if not isinstance(self.output_shape, list) or any(not isinstance(v, int) for v in self.output_shape):
            raise ValueError("output_shape must be a list of ints")
        self.avg_latency_ms = _ensure_non_negative("avg_latency_ms", self.avg_latency_ms)
        self.memory_usage_mb = _ensure_non_negative("memory_usage_mb", self.memory_usage_mb)
        if not isinstance(self.loaded, bool):
            raise ValueError("loaded must be bool")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "framework": self.framework,
            "precision": self.precision.value,
            "file_path": self.file_path,
            "file_size_bytes": self.file_size_bytes,
            "input_shape": self.input_shape,
            "output_shape": self.output_shape,
            "avg_latency_ms": self.avg_latency_ms,
            "memory_usage_mb": self.memory_usage_mb,
            "loaded": self.loaded,
        }


@dataclass
class InferenceResult:
    model_id: str
    output: Any
    latency_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be non-empty string")
        self.latency_ms = _ensure_non_negative("latency_ms", self.latency_ms)
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be datetime")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "output": self.output,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class JetsonStats:
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
    tensorrt_available: bool = False
    onnx_available: bool = False

    def __post_init__(self) -> None:
        self.gpu_utilization_pct = _ensure_non_negative("gpu_utilization_pct", self.gpu_utilization_pct)
        self.gpu_memory_used_mb = _ensure_non_negative("gpu_memory_used_mb", self.gpu_memory_used_mb)
        self.gpu_memory_total_mb = _ensure_non_negative("gpu_memory_total_mb", self.gpu_memory_total_mb)
        self.cpu_utilization_pct = _ensure_non_negative("cpu_utilization_pct", self.cpu_utilization_pct)
        self.ram_used_mb = _ensure_non_negative("ram_used_mb", self.ram_used_mb)
        self.ram_total_mb = _ensure_non_negative("ram_total_mb", self.ram_total_mb)
        self.temperature_gpu_c = float(self.temperature_gpu_c)
        self.temperature_cpu_c = float(self.temperature_cpu_c)
        self.power_draw_watts = _ensure_non_negative("power_draw_watts", self.power_draw_watts)
        self.power_budget_watts = _ensure_non_negative("power_budget_watts", self.power_budget_watts)
        if self.gpu_memory_total_mb > 0 and self.gpu_memory_used_mb > self.gpu_memory_total_mb:
            self.gpu_memory_used_mb = self.gpu_memory_total_mb
        if self.ram_total_mb > 0 and self.ram_used_mb > self.ram_total_mb:
            self.ram_used_mb = self.ram_total_mb
        if self.cuda_version is not None and not isinstance(self.cuda_version, str):
            raise ValueError("cuda_version must be a string or None")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gpu_utilization_pct": self.gpu_utilization_pct,
            "gpu_memory_used_mb": self.gpu_memory_used_mb,
            "gpu_memory_total_mb": self.gpu_memory_total_mb,
            "cpu_utilization_pct": self.cpu_utilization_pct,
            "ram_used_mb": self.ram_used_mb,
            "ram_total_mb": self.ram_total_mb,
            "temperature_gpu_c": self.temperature_gpu_c,
            "temperature_cpu_c": self.temperature_cpu_c,
            "power_draw_watts": self.power_draw_watts,
            "power_budget_watts": self.power_budget_watts,
            "cuda_version": self.cuda_version,
            "tensorrt_available": self.tensorrt_available,
            "onnx_available": self.onnx_available,
        }

    def is_thermal_throttling(self, threshold: float = 80.0) -> bool:
        threshold = float(threshold)
        return self.temperature_gpu_c >= threshold or self.temperature_cpu_c >= threshold

    def memory_pressure(self) -> float:
        system_ratio = 0.0 if self.ram_total_mb <= 0 else self.ram_used_mb / self.ram_total_mb
        gpu_ratio = 0.0 if self.gpu_memory_total_mb <= 0 else self.gpu_memory_used_mb / self.gpu_memory_total_mb
        pressure = max(system_ratio, gpu_ratio)
        if pressure < 0.0:
            return 0.0
        if pressure > 1.0:
            return 1.0
        return pressure
