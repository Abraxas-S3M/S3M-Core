"""HMMWV unmanned-ground adapter for tactical mobility control."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import random
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.platforms.common.messages import PlatformType

try:
    from src.navigation.localization.gps_monitor import GPSMonitor
    from src.navigation.localization.localization_manager import LocalizationManager
    from src.navigation.models import PlatformType as NavPlatformType
    from src.navigation.models import Pose, Waypoint
    from src.navigation.planning.path_planner import PathPlanner
    from src.navigation.planning.waypoint_navigator import WaypointNavigator

    _NAVIGATION_MODULES_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in environments without nav stack.
    GPSMonitor = None  # type: ignore[assignment]
    LocalizationManager = None  # type: ignore[assignment]
    NavPlatformType = None  # type: ignore[assignment]
    Pose = None  # type: ignore[assignment]
    Waypoint = None  # type: ignore[assignment]
    PathPlanner = None  # type: ignore[assignment]
    WaypointNavigator = None  # type: ignore[assignment]
    _NAVIGATION_MODULES_AVAILABLE = False

try:
    from src.edge_runtime.degradation_controller import DegradationController, OperatingMode
    from src.edge_runtime.hardware_profiler import HardwareProfiler, HardwareTier, NodeProfile

    _DEGRADATION_RUNTIME_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in minimal standalone deployments.
    DegradationController = None  # type: ignore[assignment]
    OperatingMode = None  # type: ignore[assignment]
    HardwareProfiler = None  # type: ignore[assignment]
    HardwareTier = None  # type: ignore[assignment]
    NodeProfile = None  # type: ignore[assignment]
    _DEGRADATION_RUNTIME_AVAILABLE = False


Tuple3 = Tuple[float, float, float]


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _as_tuple3(value: Sequence[float], field_name: str) -> Tuple3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{field_name} must be a 3-item numeric sequence")
    if not all(isinstance(item, (int, float)) for item in value):
        raise ValueError(f"{field_name} must contain numeric values")
    return (float(value[0]), float(value[1]), float(value[2]))


class HMMWVState(dict):
    """Hybrid state object supporting mapping and attribute access."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        super().__init__(payload)
        self.platform_id = str(payload.get("platform_id", ""))
        self.platform_type = PlatformType.UGV
        pose = payload.get("pose", {})
        self.position = _as_tuple3(pose.get("position_m", (0.0, 0.0, 0.0)), "position")


class HMMWVAdapter:
    """Offline simulation adapter for a wheeled UGV platform."""

    def __init__(
        self,
        platform_id: str = "hmmwv-1",
        *,
        seed: Optional[int] = None,
        use_navigation_modules: bool = True,
        use_degradation_controller: bool = True,
    ) -> None:
        if not isinstance(platform_id, str) or not platform_id.strip():
            raise ValueError("platform_id must be a non-empty string")

        self.platform_id = platform_id.strip()
        self.vehicle_id = "HMMWV-M1151A1"
        self._rng = random.Random(seed)
        self._connected = False
        self._last_update_monotonic = time.monotonic()

        # Ground-truth mobility simulation values.
        self._truth_position: Tuple3 = (0.0, 0.0, 0.0)
        self._estimated_position: Tuple3 = (0.0, 0.0, 0.0)
        self._heading_rad = 0.0
        self._speed_mps = 0.0
        self._yaw_rate_rps = 0.0
        self._odometry_drift_m = 0.0
        self._fuel_l = 120.0
        self._engine_on = True

        self._controls = {"throttle": 0.0, "brake": 0.0, "steering": 0.0}
        self._autonomy_level = 1
        self._safe_state_active = False

        self._comms_loss_until_monotonic = 0.0
        self._gps_denial_until_monotonic = 0.0
        self._gps_available = True
        self._localization_mode = "gps_fused"

        self._sensor_health: Dict[str, bool] = {
            "camera_day": True,
            "camera_thermal": True,
            "lidar_front": True,
            "radar_front": True,
            "gps": True,
            "imu": True,
            "wheel_encoder": True,
            "radio_uhf": True,
        }

        self._mission_waypoints: List[Tuple3] = []
        self._mission_idx = 0
        self._planned_route: List[Tuple3] = []

        self._degraded_mode = False
        self._degraded_reason = ""
        self._active_degraded_reasons: set[str] = set()
        self._mode_policy: Optional[object] = None
        self._operating_mode = "full_edge"

        self._gps_monitor: Optional[Any] = None
        self._localization_manager: Optional[Any] = None
        self._path_planner: Optional[Any] = None
        self._waypoint_navigator: Optional[Any] = None
        self._degradation_controller: Optional[Any] = None
        self._navigation_backend = "fallback_physics"

        if use_navigation_modules:
            self._init_navigation_modules()
        if use_degradation_controller:
            self._init_degradation_runtime()

    @property
    def navigation_modules_available(self) -> bool:
        return self._localization_manager is not None and self._path_planner is not None and self._waypoint_navigator is not None

    @property
    def degradation_controller_available(self) -> bool:
        return self._degradation_controller is not None

    def _init_navigation_modules(self) -> None:
        if not _NAVIGATION_MODULES_AVAILABLE:
            return
        try:
            self._localization_manager = LocalizationManager()
            self._path_planner = PathPlanner()
            self._waypoint_navigator = WaypointNavigator(path_planner=self._path_planner)
            self._gps_monitor = self._localization_manager.gps_monitor
            self._navigation_backend = "s3m_core_navigation"
        except Exception:
            # Tactical continuity requirement: stay operational even when nav stack is absent.
            self._localization_manager = None
            self._path_planner = None
            self._waypoint_navigator = None
            self._gps_monitor = None
            self._navigation_backend = "fallback_physics"

    def _init_degradation_runtime(self) -> None:
        if not _DEGRADATION_RUNTIME_AVAILABLE:
            return
        try:
            profile = HardwareProfiler().run()
        except Exception:
            profile = self._fallback_profile()
        if profile is None:
            return
        try:
            self._degradation_controller = DegradationController(profile)
            self._mode_policy = self._degradation_controller.current_policy()
            self._operating_mode = self._degradation_controller.current_mode.value
            self._degradation_controller.subscribe(self._on_mode_policy_update)
        except Exception:
            self._degradation_controller = None
            self._mode_policy = None

    def _fallback_profile(self) -> Optional[Any]:
        if NodeProfile is None or HardwareTier is None:
            return None
        return NodeProfile(
            tier=HardwareTier.VEHICLE_NODE,
            cpu_cores=8,
            cpu_arch="aarch64",
            ram_total_gb=16.0,
            ram_available_gb=8.0,
            disk_total_gb=64.0,
            disk_free_gb=32.0,
            gpu_detected=True,
            gpu_name="Jetson-Orin",
            gpu_memory_mb=8192,
            cuda_available=True,
            thermal_zone_c=55.0,
            power_source="vehicle",
            active_links=["uhf"],
        )

    def _on_mode_policy_update(self, mode: Any, policy: Any) -> None:
        self._operating_mode = getattr(mode, "value", str(mode))
        self._mode_policy = policy

    def connect(self) -> bool:
        self._connected = True
        self._last_update_monotonic = time.monotonic()
        if self._localization_manager is not None and not getattr(self._localization_manager, "started", False):
            self._localization_manager.start()
        return True

    def apply_mobility_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(command, dict):
            raise ValueError("command must be a dictionary")
        if not self._connected:
            return {"accepted": False, "reason": "not_connected"}

        throttle = _clamp(float(command.get("throttle", self._controls["throttle"])), 0.0, 1.0)
        brake = _clamp(float(command.get("brake", self._controls["brake"])), 0.0, 1.0)
        steering = _clamp(float(command.get("steering", self._controls["steering"])), -1.0, 1.0)

        if "waypoints" in command:
            self.plan_route(command["waypoints"])

        if self._is_comms_lost():
            throttle = 0.0
            brake = max(brake, 0.5)
        elif self._degraded_mode and self._mode_policy is not None:
            # Tactical compute budgeting: lower-speed maneuvering preserves CPU/GPU headroom.
            max_frame_rate = int(getattr(self._mode_policy, "max_frame_rate", 30))
            if max_frame_rate <= 10:
                throttle = min(throttle, 0.4)
            elif max_frame_rate <= 15:
                throttle = min(throttle, 0.6)

        if brake > 0.2:
            throttle = min(throttle, 0.2)

        self._controls.update({"throttle": throttle, "brake": brake, "steering": steering})
        return {
            "accepted": True,
            "commanded": dict(self._controls),
            "degraded_mode": self._degraded_mode,
            "operating_mode": self._operating_mode,
        }

    def plan_route(self, waypoints: Sequence[Sequence[float]]) -> Dict[str, Any]:
        if not isinstance(waypoints, (list, tuple)) or len(waypoints) < 2:
            raise ValueError("waypoints must include at least start and goal")
        parsed_waypoints = [_as_tuple3(item, "waypoint") for item in waypoints]
        self._mission_waypoints = parsed_waypoints
        self._mission_idx = 0

        if self.navigation_modules_available and Waypoint is not None and NavPlatformType is not None:
            nav_waypoints = [Waypoint(position=wp, radius=5.0) for wp in parsed_waypoints]
            nav_plan_id = self._waypoint_navigator.load_mission(
                nav_waypoints,
                platform_type=NavPlatformType.GROUND_WHEELED,
            )
            self._waypoint_navigator.start()
            self._planned_route = []
            for idx in range(len(parsed_waypoints) - 1):
                path = self._path_planner.plan(parsed_waypoints[idx], parsed_waypoints[idx + 1], obstacles=[])
                if idx == 0:
                    self._planned_route.extend(path.waypoints)
                else:
                    self._planned_route.extend(path.waypoints[1:])
            return {
                "planned": True,
                "backend": "s3m_core_navigation",
                "nav_plan_id": nav_plan_id,
                "waypoint_count": len(parsed_waypoints),
            }

        self._planned_route = list(parsed_waypoints)
        return {
            "planned": True,
            "backend": "fallback_physics",
            "waypoint_count": len(parsed_waypoints),
        }

    def set_autonomy_level(self, level: int) -> Dict[str, Any]:
        if not isinstance(level, int):
            raise ValueError("level must be an integer")
        desired = max(0, min(4, level))
        max_allowed = self._max_autonomy_level()
        self._autonomy_level = min(desired, max_allowed)
        return {
            "autonomy_level": self._autonomy_level,
            "degraded_mode": self._degraded_mode,
            "degraded_reason": self._degraded_reason,
            "max_allowed": max_allowed,
        }

    def _max_autonomy_level(self) -> int:
        if not self._degraded_mode:
            return 4
        max_allowed = 4
        if "safe_state" in self._active_degraded_reasons:
            max_allowed = min(max_allowed, 0)
        if "comms_loss" in self._active_degraded_reasons:
            max_allowed = min(max_allowed, 1)
        if "sensor_dropout" in self._active_degraded_reasons:
            max_allowed = min(max_allowed, 2)
        if self._mode_policy is not None:
            model_budget = int(getattr(self._mode_policy, "max_concurrent_models", 4))
            if model_budget <= 1:
                max_allowed = min(max_allowed, 1)
            elif model_budget <= 2:
                max_allowed = min(max_allowed, 2)
        return max_allowed

    def simulate_comms_loss(self, duration_s: float) -> Dict[str, Any]:
        if not isinstance(duration_s, (int, float)) or float(duration_s) <= 0.0:
            raise ValueError("duration_s must be positive")
        self._comms_loss_until_monotonic = time.monotonic() + float(duration_s)
        self._refresh_degraded_state()
        return {
            "comms_lost": True,
            "duration_s": float(duration_s),
            "until_monotonic": self._comms_loss_until_monotonic,
        }

    def simulate_gps_denial(self, enabled: bool, duration_s: float = 60.0) -> Dict[str, Any]:
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        if not isinstance(duration_s, (int, float)) or float(duration_s) < 0.0:
            raise ValueError("duration_s must be non-negative")

        if enabled:
            self._gps_denial_until_monotonic = time.monotonic() + float(duration_s)
            if self._gps_monitor is not None:
                self._gps_monitor.simulate_denial()
            if self._localization_manager is not None:
                # Tactical context: force dead reckoning immediately when GPS is denied.
                self._localization_manager.force_mode("dead_reckoning")
            self._localization_mode = "dead_reckoning"
        else:
            self._gps_denial_until_monotonic = 0.0
            if self._gps_monitor is not None:
                self._gps_monitor.simulate_restore()
            if self._localization_manager is not None:
                # Clear temporary override once GPS denial is lifted.
                self._localization_manager.mode_override = None
            self._localization_mode = "gps_fused"

        self._refresh_degraded_state()
        return {
            "gps_denied": self._is_gps_denied(),
            "duration_s": float(duration_s),
        }

    def apply_sensor_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(command, dict):
            raise ValueError("command must be a dictionary")
        sensor_name = command.get("sensor")
        enabled = command.get("enabled")
        if not isinstance(sensor_name, str) or sensor_name not in self._sensor_health:
            raise ValueError("sensor must be a known sensor name")
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")

        self._sensor_health[sensor_name] = enabled
        self._refresh_degraded_state()
        return {
            "accepted": True,
            "sensor": sensor_name,
            "enabled": enabled,
            "degraded_mode": self._degraded_mode,
            "degraded_reason": self._degraded_reason,
        }

    def safe_state(self, reason: str = "operator_override") -> Dict[str, Any]:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        self._safe_state_active = True
        self._controls = {"throttle": 0.0, "brake": 1.0, "steering": 0.0}
        self._autonomy_level = 0
        self._refresh_degraded_state()
        return {
            "safe_state": True,
            "reason": reason.strip(),
            "controls": dict(self._controls),
            "autonomy_level": self._autonomy_level,
        }

    def _is_comms_lost(self) -> bool:
        return time.monotonic() < self._comms_loss_until_monotonic

    def _is_gps_denied(self) -> bool:
        return time.monotonic() < self._gps_denial_until_monotonic

    def _sensor_dropout_detected(self) -> bool:
        critical = ("camera_day", "camera_thermal", "lidar_front", "radar_front")
        down = sum(1 for name in critical if not self._sensor_health.get(name, False))
        return down >= 3

    def _refresh_degraded_state(self) -> None:
        previous = set(self._active_degraded_reasons)
        reasons: set[str] = set()
        if self._safe_state_active:
            reasons.add("safe_state")
        if self._is_comms_lost():
            reasons.add("comms_loss")
        if self._is_gps_denied():
            reasons.add("gps_denial")
        if self._sensor_dropout_detected():
            reasons.add("sensor_dropout")

        self._active_degraded_reasons = reasons
        self._degraded_mode = bool(reasons)
        self._degraded_reason = self._prioritize_degraded_reason(reasons)
        if previous != reasons:
            self._sync_degradation_controller()
        self._autonomy_level = min(self._autonomy_level, self._max_autonomy_level())

    @staticmethod
    def _prioritize_degraded_reason(reasons: set[str]) -> str:
        priority = ("safe_state", "comms_loss", "sensor_dropout", "gps_denial")
        for item in priority:
            if item in reasons:
                return item
        return ""

    def _sync_degradation_controller(self) -> None:
        if self._degradation_controller is None or OperatingMode is None:
            return

        if not self._degraded_mode:
            self._degradation_controller.force_mode(OperatingMode.MODE_A_FULL_EDGE, reason="hmmwv_nominal")
            return

        if self._degraded_reason == "safe_state":
            target_mode = OperatingMode.MODE_D_OFFLINE_SURVIVAL
        elif self._degraded_reason == "comms_loss":
            target_mode = OperatingMode.MODE_C_INTERMITTENT_LINK
        elif self._degraded_reason == "sensor_dropout":
            target_mode = OperatingMode.MODE_B_CPU_CONSTRAINED
        else:
            target_mode = OperatingMode.MODE_B_CPU_CONSTRAINED

        self._degradation_controller.force_mode(target_mode, reason=f"hmmwv_{self._degraded_reason}")
        self._mode_policy = self._degradation_controller.current_policy()
        self._operating_mode = self._degradation_controller.current_mode.value

    def _step_simulation(self) -> None:
        if not self._connected:
            return
        now = time.monotonic()
        dt = _clamp(now - self._last_update_monotonic, 0.01, 1.0)
        self._last_update_monotonic = now

        self._refresh_degraded_state()
        self._apply_waypoint_guidance()
        accel_cmd = self._integrate_physics(dt)
        self._update_navigation_state(dt, accel_cmd)

    def _apply_waypoint_guidance(self) -> None:
        if self._autonomy_level < 2:
            return
        if self.navigation_modules_available and self._waypoint_navigator is not None and self._mission_waypoints:
            if Pose is None:
                return
            current_pose = Pose(
                position=self._estimated_position,
                orientation=(0.0, 0.0, self._heading_rad),
                velocity=(
                    self._speed_mps * math.cos(self._heading_rad),
                    self._speed_mps * math.sin(self._heading_rad),
                    0.0,
                ),
                angular_velocity=(0.0, 0.0, self._yaw_rate_rps),
                timestamp=datetime.now(timezone.utc),
                confidence=0.8,
                source="hmmwv_adapter",
            )
            guidance = self._waypoint_navigator.update(current_pose)
            target_position = _as_tuple3(guidance["target_position"], "target_position")
            self._set_guidance_controls(target_position, active=(guidance.get("status") == "active"))
            return

        if not self._mission_waypoints:
            return
        target = self._mission_waypoints[min(self._mission_idx, len(self._mission_waypoints) - 1)]
        distance = math.dist(self._truth_position, target)
        if distance < 4.0 and self._mission_idx < len(self._mission_waypoints) - 1:
            self._mission_idx += 1
            target = self._mission_waypoints[self._mission_idx]
        self._set_guidance_controls(target, active=True)

    def _set_guidance_controls(self, target: Tuple3, *, active: bool) -> None:
        if not active:
            self._controls["throttle"] = 0.0
            self._controls["brake"] = max(self._controls["brake"], 0.4)
            self._controls["steering"] = 0.0
            return
        dx = target[0] - self._truth_position[0]
        dy = target[1] - self._truth_position[1]
        heading_target = math.atan2(dy, dx)
        heading_error = math.atan2(
            math.sin(heading_target - self._heading_rad),
            math.cos(heading_target - self._heading_rad),
        )
        self._controls["steering"] = _clamp(heading_error / max(math.pi / 2.0, 1e-6), -1.0, 1.0)
        self._controls["throttle"] = max(self._controls["throttle"], 0.45)
        self._controls["brake"] = min(self._controls["brake"], 0.2)

    def _integrate_physics(self, dt: float) -> float:
        throttle = self._controls["throttle"]
        brake = self._controls["brake"]
        steering = self._controls["steering"]

        traction_accel = 3.8 * throttle
        brake_decel = 7.0 * brake
        drag = 0.06 * self._speed_mps
        net_accel = traction_accel - brake_decel - drag
        self._speed_mps = _clamp(self._speed_mps + net_accel * dt, 0.0, 29.0)

        self._yaw_rate_rps = steering * 0.35 * min(1.0, max(self._speed_mps, 1.0) / 4.0)
        self._heading_rad += self._yaw_rate_rps * dt

        dx = self._speed_mps * math.cos(self._heading_rad) * dt
        dy = self._speed_mps * math.sin(self._heading_rad) * dt
        self._truth_position = (
            self._truth_position[0] + dx,
            self._truth_position[1] + dy,
            0.0,
        )

        burn_rate_lps = 0.0015 + (0.012 * throttle) + (0.001 * abs(steering)) + (0.0007 * self._speed_mps)
        self._fuel_l = max(0.0, self._fuel_l - burn_rate_lps * dt)
        return net_accel

    def _update_navigation_state(self, dt: float, net_accel: float) -> None:
        gps_available = (not self._is_gps_denied()) and self._sensor_health.get("gps", True)
        imu_available = self._sensor_health.get("imu", True)
        if self._gps_monitor is not None and not gps_available:
            self._gps_monitor.simulate_denial()

        if self._localization_manager is not None and imu_available:
            imu_data = {
                "linear_accel": (net_accel + self._rng.uniform(-0.05, 0.05), 0.0, 0.0),
                "angular_vel": (0.0, 0.0, self._yaw_rate_rps),
                "dt": dt,
            }
            gps_data = None
            if gps_available:
                gps_data = {
                    "satellites": 9,
                    "hdop": 1.2,
                    "fix_type": "3d",
                    "position": self._truth_position,
                }
            nav_state = self._localization_manager.update(imu_data=imu_data, gps_data=gps_data)
            self._estimated_position = nav_state.pose.position
            self._odometry_drift_m = float(nav_state.drift_estimate_meters)
            self._localization_mode = str(nav_state.localization_mode)
            self._gps_available = not nav_state.gps_status.is_denied()
            if not self._gps_available:
                # Tactical context: when GPS is denied, maintain a conservative drift budget.
                self._odometry_drift_m = max(
                    self._odometry_drift_m,
                    self._odometry_drift_m + (0.02 + (0.01 * self._speed_mps)) * dt,
                )
            return

        # Tactical fallback when S3M-Core navigation modules are unavailable.
        self._gps_available = gps_available
        if gps_available:
            self._estimated_position = self._truth_position
            self._odometry_drift_m = max(0.0, self._odometry_drift_m - 0.4 * dt)
            self._localization_mode = "gps_fused"
        else:
            drift_step = max(0.03, 0.01 * self._speed_mps) * dt
            self._odometry_drift_m += drift_step
            drift_x = self._rng.uniform(-self._odometry_drift_m, self._odometry_drift_m) * 0.02
            drift_y = self._rng.uniform(-self._odometry_drift_m, self._odometry_drift_m) * 0.02
            self._estimated_position = (
                self._truth_position[0] + drift_x,
                self._truth_position[1] + drift_y,
                self._truth_position[2],
            )
            self._localization_mode = "dead_reckoning"

    def _compute_budget_view(self) -> Dict[str, Any]:
        if self._mode_policy is None:
            return {
                "max_concurrent_models": 4,
                "max_frame_rate": 30,
                "allow_gpu": True,
                "queue_outbound": False,
                "max_autonomy_level": self._max_autonomy_level(),
            }
        return {
            "max_concurrent_models": int(getattr(self._mode_policy, "max_concurrent_models", 1)),
            "max_frame_rate": int(getattr(self._mode_policy, "max_frame_rate", 5)),
            "allow_gpu": bool(getattr(self._mode_policy, "allow_gpu", False)),
            "queue_outbound": bool(getattr(self._mode_policy, "queue_outbound", True)),
            "max_autonomy_level": self._max_autonomy_level(),
        }

    def read_state(self) -> HMMWVState:
        self._step_simulation()
        nav_sensors = {
            "gps_x_m": self._estimated_position[0] if self._gps_available else None,
            "gps_y_m": self._estimated_position[1] if self._gps_available else None,
            "imu_yaw_rate_rps": self._yaw_rate_rps if self._sensor_health.get("imu", True) else None,
            "wheel_speed_mps": self._speed_mps if self._sensor_health.get("wheel_encoder", True) else None,
        }
        payload = {
            "platform_id": self.platform_id,
            "vehicle_id": self.vehicle_id,
            "platform_type": PlatformType.UGV.value,
            "connected": self._connected,
            "pose": {
                "position_m": self._estimated_position,
                "heading_rad": self._heading_rad,
            },
            "kinematics": {
                "speed_mps": self._speed_mps,
                "yaw_rate_rps": self._yaw_rate_rps,
            },
            "powertrain": {
                "engine_on": self._engine_on,
                "fuel_l": self._fuel_l,
            },
            "autonomy": {
                "autonomy_level": self._autonomy_level,
                "degraded_mode": self._degraded_mode,
                "degraded_reason": self._degraded_reason,
                "safe_state": self._safe_state_active,
                "operating_mode": self._operating_mode,
                "degradation_controller": self.degradation_controller_available,
                "compute_budget": self._compute_budget_view(),
            },
            "navigation": {
                "backend": self._navigation_backend,
                "localization_mode": self._localization_mode,
                "gps_available": self._gps_available,
                "odometry_drift_m": self._odometry_drift_m,
                "mission_waypoint_index": self._mission_idx,
                "planned_route_points": len(self._planned_route),
            },
            "sensors": {
                "sensor_health": dict(self._sensor_health),
                "navigation": nav_sensors,
            },
            "controls": dict(self._controls),
        }
        return HMMWVState(payload)
