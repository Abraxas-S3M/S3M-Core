"""Fleet manager for interceptor drone launch, guidance, and assessment.

Military context:
Coordinates command-guided interceptors as a layered air-defense channel,
including launch authorization, guidance updates, and miss re-engagement flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from threading import RLock
from time import time
from typing import Any, Dict, Optional, Tuple

from services.interceptor.autopilot_adapter import AutopilotAdapter
from services.interceptor.guidance_computer import InterceptorGuidanceComputer
from services.interceptor.models import (
    GuidancePhase,
    GuidanceSolution,
    InterceptResult,
    InterceptorConfig,
    InterceptorState,
)
from src.apps.drone_ops.autopilot_bridge import AutopilotBridge

Vector3 = Tuple[float, float, float]


def _vector_norm(v: Vector3) -> float:
    return sqrt((v[0] * v[0]) + (v[1] * v[1]) + (v[2] * v[2]))


def _target_speed(v: Vector3) -> float:
    return _vector_norm(v)


def _is_launched(state: InterceptorState) -> bool:
    return state != InterceptorState.PRELAUNCH


def _is_radar_acquired(state: InterceptorState) -> bool:
    return state in {
        InterceptorState.RADAR_ACQUIRED,
        InterceptorState.MIDCOURSE_GUIDED,
        InterceptorState.TERMINAL_APPROACH,
        InterceptorState.AUTONOMOUS_HANDOFF,
        InterceptorState.ENGAGED,
    }


@dataclass
class _InterceptorRuntime:
    interceptor_id: str
    config: InterceptorConfig
    autopilot: AutopilotBridge
    guidance: InterceptorGuidanceComputer
    state: InterceptorState = InterceptorState.PRELAUNCH
    target_id: Optional[str] = None
    target_position_m: Optional[Vector3] = None
    target_velocity_mps: Vector3 = (0.0, 0.0, 0.0)
    target_classification: str = "unknown"
    last_solution: Optional[GuidanceSolution] = None
    last_allocation: Any = None
    last_position_m: Optional[Vector3] = None
    last_position_time_s: Optional[float] = None


class InterceptorManager:
    """Manage a fleet of command-guided interceptor drones."""

    def __init__(
        self,
        *,
        sensor_manager: Any | None = None,
        track_fuser: Any | None = None,
        target_allocator: Any | None = None,
        miss_handler: Any | None = None,
    ) -> None:
        self._lock = RLock()
        self._sensor_manager = sensor_manager
        self._track_fuser = track_fuser
        self._target_allocator = target_allocator
        self._miss_handler = miss_handler
        self._autopilot_adapter = AutopilotAdapter()
        self._interceptors: Dict[str, _InterceptorRuntime] = {}

    def register_interceptor(
        self,
        interceptor_id: str,
        config: InterceptorConfig,
        autopilot: Optional[AutopilotBridge] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            if interceptor_id in self._interceptors:
                raise ValueError(f"interceptor_id '{interceptor_id}' already registered")
            bridge = autopilot or AutopilotBridge(backend="simulated")
            bridge.connect()
            runtime = _InterceptorRuntime(
                interceptor_id=interceptor_id,
                config=config,
                autopilot=bridge,
                guidance=InterceptorGuidanceComputer(interceptor_id=interceptor_id, config=config),
            )
            self._interceptors[interceptor_id] = runtime
            return self.get_interceptor_status(interceptor_id)

    def launch_interceptor(self, interceptor_id: str, takeoff_altitude_m: float = 120.0) -> Dict[str, Any]:
        with self._lock:
            runtime = self._require_interceptor(interceptor_id)
            runtime.autopilot.arm()
            runtime.autopilot.takeoff(takeoff_altitude_m)
            runtime.state = InterceptorState.LAUNCHED
            return self.get_interceptor_status(interceptor_id)

    def assign_target(
        self,
        interceptor_id: str,
        target_id: str,
        target_position_m: Vector3,
        target_velocity_mps: Vector3 = (0.0, 0.0, 0.0),
        target_classification: str = "unknown",
        request_allocation: bool = True,
    ) -> Dict[str, Any]:
        with self._lock:
            runtime = self._require_interceptor(interceptor_id)
            runtime.target_id = target_id
            runtime.target_position_m = target_position_m
            runtime.target_velocity_mps = target_velocity_mps
            runtime.target_classification = target_classification
            if runtime.state == InterceptorState.LAUNCHED:
                runtime.state = InterceptorState.RADAR_ACQUIRED
            if request_allocation and self._target_allocator is not None:
                runtime.last_allocation = self._request_allocation(
                    target_id=target_id,
                    target_position_m=target_position_m,
                    target_velocity_mps=target_velocity_mps,
                    target_classification=target_classification,
                )
            return self.get_interceptor_status(interceptor_id)

    def update_target_from_fusion(self, target_id: str) -> Optional[Tuple[Vector3, Vector3]]:
        if self._track_fuser is not None and hasattr(self._track_fuser, "get_track"):
            track = self._track_fuser.get_track(target_id)
            if track is not None:
                return track.position, track.velocity
        if self._sensor_manager is not None and hasattr(self._sensor_manager, "get_fused_tracks"):
            tracks = self._sensor_manager.get_fused_tracks()
            for track in tracks:
                if getattr(track, "track_id", None) == target_id:
                    return track.position, track.velocity
        return None

    def _estimate_interceptor_velocity(self, runtime: _InterceptorRuntime, position_m: Vector3) -> Vector3:
        now_s = time()
        if runtime.last_position_m is None or runtime.last_position_time_s is None:
            runtime.last_position_m = position_m
            runtime.last_position_time_s = now_s
            return (0.0, 0.0, 0.0)
        dt = max(1e-3, now_s - runtime.last_position_time_s)
        velocity = (
            (position_m[0] - runtime.last_position_m[0]) / dt,
            (position_m[1] - runtime.last_position_m[1]) / dt,
            (position_m[2] - runtime.last_position_m[2]) / dt,
        )
        runtime.last_position_m = position_m
        runtime.last_position_time_s = now_s
        return velocity

    def guide_interceptor(self, interceptor_id: str, dt_s: Optional[float] = None) -> GuidanceSolution:
        with self._lock:
            runtime = self._require_interceptor(interceptor_id)
            if runtime.target_id is None or runtime.target_position_m is None:
                raise ValueError("target must be assigned before guidance")

            fused_target = self.update_target_from_fusion(runtime.target_id)
            if fused_target is not None:
                runtime.target_position_m, runtime.target_velocity_mps = fused_target

            telemetry = runtime.autopilot.get_telemetry()
            interceptor_position = tuple(telemetry.get("position", (0.0, 0.0, 0.0)))
            interceptor_velocity = self._estimate_interceptor_velocity(runtime, interceptor_position)  # type: ignore[arg-type]

            solution = runtime.guidance.compute_solution(
                target_id=runtime.target_id,
                interceptor_position_m=interceptor_position,  # type: ignore[arg-type]
                interceptor_velocity_mps=interceptor_velocity,
                target_position_m=runtime.target_position_m,
                target_velocity_mps=runtime.target_velocity_mps,
                launched=_is_launched(runtime.state),
                radar_acquired=_is_radar_acquired(runtime.state),
                engaged=runtime.state == InterceptorState.ENGAGED,
                dt_s=dt_s,
            )
            runtime.last_solution = solution
            runtime.state = runtime.guidance.get_state()[0]
            self._autopilot_adapter.send_solution(runtime.autopilot, interceptor_position, solution)  # type: ignore[arg-type]
            return solution

    def guide_all(self, dt_s: Optional[float] = None) -> Dict[str, GuidanceSolution]:
        with self._lock:
            solutions: Dict[str, GuidanceSolution] = {}
            for interceptor_id in list(self._interceptors.keys()):
                runtime = self._interceptors[interceptor_id]
                if runtime.target_id is None:
                    continue
                solutions[interceptor_id] = self.guide_interceptor(interceptor_id, dt_s=dt_s)
            return solutions

    def assess_intercept_result(self, interceptor_id: str) -> InterceptResult:
        with self._lock:
            runtime = self._require_interceptor(interceptor_id)
            if runtime.last_solution is None:
                raise ValueError("no guidance solution available for assessment")
            state = runtime.state
            if runtime.last_solution.phase == GuidancePhase.ENGAGED:
                state = InterceptorState.ENGAGED
            elif runtime.last_solution.phase == GuidancePhase.MISS:
                state = InterceptorState.MISS
            return InterceptResult(
                interceptor_id=interceptor_id,
                target_id=runtime.last_solution.target_id,
                state=state,
                miss_distance_m=runtime.last_solution.geometry.predicted_miss_distance_m,
                engagement_range_m=runtime.last_solution.geometry.range_m,
                details={
                    "phase": runtime.last_solution.phase.value,
                    "mode": runtime.last_solution.mode.value,
                    "reason": runtime.last_solution.reason,
                },
            )

    def report_miss_and_reengage(
        self,
        interceptor_id: str,
        updated_target_position_m: Optional[Vector3] = None,
        updated_target_velocity_mps: Optional[Vector3] = None,
    ) -> Any:
        with self._lock:
            runtime = self._require_interceptor(interceptor_id)
            runtime.state = InterceptorState.MISS
            if self._miss_handler is None or runtime.last_allocation is None:
                return None
            if hasattr(self._miss_handler, "report_miss"):
                speed = _target_speed(updated_target_velocity_mps or runtime.target_velocity_mps)
                return self._miss_handler.report_miss(
                    runtime.last_allocation,
                    updated_target_position=updated_target_position_m or runtime.target_position_m,
                    updated_target_speed=speed,
                )
            if hasattr(self._miss_handler, "handle_miss"):
                return self._miss_handler.handle_miss(
                    target_id=runtime.target_id or "unknown",
                    target_position=updated_target_position_m or runtime.target_position_m,
                    target_type=runtime.target_classification,
                    previous_allocation=runtime.last_allocation,
                    miss_reason="interceptor_miss",
                )
            return None

    def get_interceptor_status(self, interceptor_id: str) -> Dict[str, Any]:
        with self._lock:
            runtime = self._require_interceptor(interceptor_id)
            return {
                "interceptor_id": runtime.interceptor_id,
                "state": runtime.state.value,
                "target_id": runtime.target_id,
                "target_position_m": runtime.target_position_m,
                "target_velocity_mps": runtime.target_velocity_mps,
                "last_solution": runtime.last_solution.to_dict() if runtime.last_solution else None,
            }

    def list_interceptors(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {interceptor_id: self.get_interceptor_status(interceptor_id) for interceptor_id in self._interceptors}

    def health_check(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "interceptors_registered": len(self._interceptors),
                "interceptors_with_targets": sum(1 for r in self._interceptors.values() if r.target_id is not None),
                "states": {interceptor_id: runtime.state.value for interceptor_id, runtime in self._interceptors.items()},
            }

    def _request_allocation(
        self,
        *,
        target_id: str,
        target_position_m: Vector3,
        target_velocity_mps: Vector3,
        target_classification: str,
    ) -> Any:
        speed = _target_speed(target_velocity_mps)
        allocator = self._target_allocator
        if allocator is None:
            return None
        if hasattr(allocator, "allocate"):
            return allocator.allocate(
                target_id=target_id,
                target_position=target_position_m,
                target_speed_mps=speed,
                target_classification=target_classification,
            )
        if hasattr(allocator, "allocate_target"):
            return allocator.allocate_target(
                target_id=target_id,
                target_position=target_position_m,
                target_type=target_classification,
            )
        return None

    def _require_interceptor(self, interceptor_id: str) -> _InterceptorRuntime:
        runtime = self._interceptors.get(interceptor_id)
        if runtime is None:
            raise KeyError(f"unknown interceptor_id '{interceptor_id}'")
        return runtime
