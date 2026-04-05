"""HMMWV M1151 A1 UGV adapter with offline tactical autonomy simulation."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

try:  # Dependency from Prompt 1.
    from src.platforms.common.contracts import PlatformAdapter
except Exception:
    @runtime_checkable
    class PlatformAdapter(Protocol):
        """Fallback protocol to keep this adapter importable in isolation."""

        def connect(self) -> bool:
            ...

        def read_state(self) -> dict[str, Any]:
            ...

        def apply_mobility_command(self, command: dict[str, Any]) -> dict[str, Any]:
            ...

        def apply_sensor_command(self, command: dict[str, Any]) -> dict[str, Any]:
            ...

        def safe_state(self, reason: str = "manual_intervention") -> dict[str, Any]:
            ...


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _wrap_heading(angle_rad: float) -> float:
    return (angle_rad + math.pi) % (2.0 * math.pi) - math.pi


@dataclass(frozen=True)
class _PhysicsProfile:
    mass_kg: float = 5_200.0
    wheelbase_m: float = 3.30
    max_accel_mps2: float = 2.7
    max_brake_mps2: float = 6.4
    rolling_decel_mps2: float = 0.16
    aero_drag_coeff: float = 0.013
    max_speed_mps: float = 31.0
    max_steer_rad: float = 0.52
    idle_fuel_lph: float = 1.8
    ambient_temp_c: float = 31.0


@dataclass
class _VehicleState:
    connected: bool
    x_m: float
    y_m: float
    heading_rad: float
    speed_mps: float
    accel_mps2: float
    yaw_rate_rps: float
    fuel_l: float
    engine_temp_c: float
    battery_v: float
    autonomy_level: int
    degraded_mode: bool
    degraded_reason: str | None
    gps_available: bool
    comms_available: bool
    slam_quality: float
    dbw_engaged: bool
    obstacle_distance_m: float


class HMMWVAdapter(PlatformAdapter):
    """Ground platform adapter for HMMWV M1151 A1 UGV rehearsal and integration."""

    SENSOR_NAMES: tuple[str, ...] = (
        "camera_day",
        "camera_thermal",
        "lidar_front",
        "radar_front",
        "imu",
        "wheel_encoder",
        "gps",
        "acoustic",
    )

    AUTONOMY_LEVELS: dict[int, str] = {
        0: "manual_only",
        1: "driver_assist",
        2: "guarded_autonomy",
        3: "mission_autonomy_supervised",
        4: "full_autonomy",
    }

    def __init__(self, vehicle_id: str = "HMMWV-M1151A1", seed: int | None = None) -> None:
        self.vehicle_id = vehicle_id
        self._rng = random.Random(1151 if seed is None else seed)
        self._physics = _PhysicsProfile()
        self._state = _VehicleState(
            connected=False,
            x_m=0.0,
            y_m=0.0,
            heading_rad=0.0,
            speed_mps=0.0,
            accel_mps2=0.0,
            yaw_rate_rps=0.0,
            fuel_l=95.0,
            engine_temp_c=52.0,
            battery_v=24.6,
            autonomy_level=0,
            degraded_mode=False,
            degraded_reason=None,
            gps_available=True,
            comms_available=True,
            slam_quality=0.92,
            dbw_engaged=False,
            obstacle_distance_m=140.0,
        )
        self._sensor_enabled = {name: True for name in self.SENSOR_NAMES}
        self._sensor_health = {name: 1.0 for name in self.SENSOR_NAMES}
        self._throttle_cmd = 0.0
        self._brake_cmd = 1.0
        self._steer_cmd = 0.0
        self._gps_denied_until_monotonic = 0.0
        self._comms_lost_until_monotonic = 0.0
        self._slam_x_m = self._state.x_m
        self._slam_y_m = self._state.y_m
        self._slam_heading_rad = self._state.heading_rad
        self._odometry_drift_m = 0.0
        self._last_update_monotonic = time.monotonic()
        self._step_index = 0

    def connect(self) -> bool:
        self._state.connected = True
        self._last_update_monotonic = time.monotonic()
        self._state.dbw_engaged = True
        return True

    def read_state(self) -> dict[str, Any]:
        self._step()
        fused = self._fuse_sensors()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "vehicle_id": self.vehicle_id,
            "connected": self._state.connected,
            "pose": {
                "x_m": round(self._state.x_m, 3),
                "y_m": round(self._state.y_m, 3),
                "heading_rad": round(self._state.heading_rad, 4),
            },
            "kinematics": {
                "speed_mps": round(self._state.speed_mps, 3),
                "accel_mps2": round(self._state.accel_mps2, 3),
                "yaw_rate_rps": round(self._state.yaw_rate_rps, 4),
            },
            "powertrain": {
                "fuel_l": round(self._state.fuel_l, 3),
                "engine_temp_c": round(self._state.engine_temp_c, 3),
                "battery_v": round(self._state.battery_v, 3),
            },
            "autonomy": {
                "level": self._state.autonomy_level,
                "label": self.AUTONOMY_LEVELS[self._state.autonomy_level],
                "degraded_mode": self._state.degraded_mode,
                "degraded_reason": self._state.degraded_reason,
            },
            "navigation": {
                "gps_available": self._state.gps_available,
                "comms_available": self._state.comms_available,
                "slam_quality": round(self._state.slam_quality, 3),
                "odometry_drift_m": round(self._odometry_drift_m, 3),
            },
            "sensors": fused,
        }

    def apply_mobility_command(self, command: dict[str, Any]) -> dict[str, Any]:
        self._step()
        if not self._state.connected:
            return {"accepted": False, "reason": "not_connected"}

        if bool(command.get("emergency_stop", False)):
            return self.safe_state(reason="emergency_stop")

        throttle = _clamp(float(command.get("throttle", self._throttle_cmd)), 0.0, 1.0)
        brake = _clamp(float(command.get("brake", self._brake_cmd)), 0.0, 1.0)
        steering = _clamp(float(command.get("steering", self._steer_cmd)), -1.0, 1.0)

        if self._state.degraded_mode:
            # In degraded combat conditions, speed authority is intentionally reduced for survivability.
            throttle = min(throttle, 0.45)
            steering = _clamp(steering, -0.55, 0.55)

        if not self._state.comms_available:
            throttle = 0.0
            brake = max(brake, 0.5)

        self._throttle_cmd = throttle
        self._brake_cmd = brake
        self._steer_cmd = steering
        self._state.dbw_engaged = bool(command.get("dbw_enable", True))

        return {
            "accepted": True,
            "commanded": {
                "throttle": round(self._throttle_cmd, 3),
                "brake": round(self._brake_cmd, 3),
                "steering": round(self._steer_cmd, 3),
            },
            "degraded_mode": self._state.degraded_mode,
            "autonomy_level": self._state.autonomy_level,
        }

    def apply_sensor_command(self, command: dict[str, Any]) -> dict[str, Any]:
        sensor = str(command.get("sensor", "")).strip().lower()
        enabled = bool(command.get("enabled", True))
        health_drop = float(command.get("health_drop", 0.0))
        reset = bool(command.get("reset_all", False))

        if reset:
            self._sensor_enabled = {name: True for name in self.SENSOR_NAMES}
            self._sensor_health = {name: 1.0 for name in self.SENSOR_NAMES}
            self._state.degraded_mode = False
            self._state.degraded_reason = None
        elif sensor in self._sensor_enabled:
            self._sensor_enabled[sensor] = enabled
            new_health = self._sensor_health[sensor] - max(0.0, health_drop)
            self._sensor_health[sensor] = _clamp(new_health, 0.0, 1.0)
        else:
            return {"accepted": False, "reason": "unknown_sensor", "sensor": sensor}

        self._evaluate_degraded_mode()
        healthy_count = sum(
            1
            for name in self.SENSOR_NAMES
            if self._sensor_enabled[name] and self._sensor_health[name] >= 0.35
        )
        return {
            "accepted": True,
            "healthy_sensor_count": healthy_count,
            "degraded_mode": self._state.degraded_mode,
            "sensor_health": {k: round(v, 3) for k, v in self._sensor_health.items()},
        }

    def safe_state(self, reason: str = "manual_intervention") -> dict[str, Any]:
        self._throttle_cmd = 0.0
        self._brake_cmd = 1.0
        self._steer_cmd = 0.0
        self._state.dbw_engaged = False
        self._enter_degraded_mode(reason=reason, fallback_level=0)
        return {
            "safe_state": True,
            "reason": reason,
            "autonomy_level": self._state.autonomy_level,
            "controls": {"throttle": 0.0, "brake": 1.0, "steering": 0.0},
        }

    def simulate_gps_denial(self, enabled: bool = True, duration_s: float = 120.0) -> dict[str, Any]:
        if enabled:
            self._state.gps_available = False
            self._gps_denied_until_monotonic = time.monotonic() + max(0.0, duration_s)
        else:
            self._state.gps_available = True
            self._gps_denied_until_monotonic = 0.0
        self._evaluate_degraded_mode()
        return {
            "gps_denied": not self._state.gps_available,
            "duration_s": float(max(0.0, duration_s)) if enabled else 0.0,
        }

    def simulate_comms_loss(self, duration_s: float = 45.0) -> dict[str, Any]:
        self._state.comms_available = False
        self._comms_lost_until_monotonic = time.monotonic() + max(0.0, duration_s)
        self._enter_degraded_mode(reason="comms_loss", fallback_level=1)
        return {"comms_lost": True, "duration_s": float(max(0.0, duration_s))}

    def set_autonomy_level(self, level: int) -> dict[str, Any]:
        target = int(_clamp(float(level), 0.0, 4.0))
        if self._state.degraded_mode and target > 2:
            target = 2
        if not self._state.comms_available and target > 1:
            target = 1
        self._state.autonomy_level = target
        return {
            "autonomy_level": target,
            "label": self.AUTONOMY_LEVELS[target],
            "degraded_mode": self._state.degraded_mode,
        }

    def _step(self) -> None:
        now = time.monotonic()
        dt = _clamp(now - self._last_update_monotonic, 0.01, 1.0)
        self._last_update_monotonic = now
        self._step_index += 1
        self._resolve_timers(now)
        self._update_physics(dt)
        self._simulate_thermal(dt)
        self._update_navigation(dt)
        self._evaluate_degraded_mode()

    def _resolve_timers(self, now: float) -> None:
        if self._gps_denied_until_monotonic > 0.0 and now >= self._gps_denied_until_monotonic:
            self._state.gps_available = True
            self._gps_denied_until_monotonic = 0.0
        if self._comms_lost_until_monotonic > 0.0 and now >= self._comms_lost_until_monotonic:
            self._state.comms_available = True
            self._comms_lost_until_monotonic = 0.0

    def _update_physics(self, dt: float) -> None:
        if not self._state.connected:
            return

        if self._state.fuel_l <= 0.0:
            self._throttle_cmd = 0.0
            self._state.fuel_l = 0.0
            self._enter_degraded_mode(reason="fuel_depleted", fallback_level=0)

        max_speed = self._physics.max_speed_mps if not self._state.degraded_mode else 12.5
        traction = self._physics.max_accel_mps2 * self._throttle_cmd
        braking = self._physics.max_brake_mps2 * self._brake_cmd
        aero_drag = self._physics.aero_drag_coeff * (self._state.speed_mps ** 2)
        accel = traction - braking - self._physics.rolling_decel_mps2 - aero_drag
        if self._state.speed_mps <= 0.05 and accel < 0.0:
            accel = 0.0

        self._state.accel_mps2 = accel
        self._state.speed_mps = _clamp(self._state.speed_mps + accel * dt, 0.0, max_speed)
        steer_rad = self._steer_cmd * self._physics.max_steer_rad
        if abs(steer_rad) > 1e-4 and self._state.speed_mps > 0.1:
            self._state.yaw_rate_rps = (
                self._state.speed_mps / self._physics.wheelbase_m * math.tan(steer_rad)
            )
        else:
            self._state.yaw_rate_rps = 0.0
        self._state.heading_rad = _wrap_heading(self._state.heading_rad + self._state.yaw_rate_rps * dt)

        self._state.x_m += self._state.speed_mps * math.cos(self._state.heading_rad) * dt
        self._state.y_m += self._state.speed_mps * math.sin(self._state.heading_rad) * dt

        load_factor = 0.25 + 0.9 * self._throttle_cmd + 0.15 * abs(self._steer_cmd)
        burn_lps = (self._physics.idle_fuel_lph / 3600.0) * (1.0 + load_factor)
        burn_lps += 0.00008 * self._state.speed_mps
        self._state.fuel_l = _clamp(self._state.fuel_l - burn_lps * dt, 0.0, 95.0)
        self._state.battery_v = _clamp(24.8 - 0.9 * self._throttle_cmd - 0.1 * self._brake_cmd, 23.1, 25.2)

    def _simulate_thermal(self, dt: float) -> None:
        heat_in = 1.7 + 8.5 * self._throttle_cmd + 0.8 * self._brake_cmd
        cooling = (self._state.engine_temp_c - self._physics.ambient_temp_c) * (
            0.018 + 0.012 * self._state.speed_mps
        )
        self._state.engine_temp_c += (heat_in - cooling) * dt
        self._state.engine_temp_c = _clamp(self._state.engine_temp_c, 20.0, 130.0)
        if self._state.engine_temp_c >= 114.0:
            self._enter_degraded_mode(reason="thermal_limit", fallback_level=0)
        elif self._state.engine_temp_c >= 108.0:
            self._enter_degraded_mode(reason="thermal_warning", fallback_level=1)

    def _update_navigation(self, dt: float) -> None:
        if self._state.gps_available and self._sensor_enabled["gps"] and self._sensor_health["gps"] > 0.25:
            # GPS-valid operation aligns SLAM map to support tactical convoy lane keeping.
            self._slam_x_m += 0.55 * (self._state.x_m - self._slam_x_m)
            self._slam_y_m += 0.55 * (self._state.y_m - self._slam_y_m)
            heading_error = _wrap_heading(self._state.heading_rad - self._slam_heading_rad)
            self._slam_heading_rad = _wrap_heading(self._slam_heading_rad + 0.5 * heading_error)
            self._odometry_drift_m *= 0.86
            self._state.slam_quality = _clamp(self._state.slam_quality + 0.01, 0.2, 0.99)
            return

        drift_growth = 0.06 + (1.0 - self._sensor_health["imu"]) * 0.15
        self._odometry_drift_m += drift_growth * dt
        nav_noise = self._rng.uniform(-0.2, 0.2) * self._odometry_drift_m
        self._slam_x_m += self._state.speed_mps * math.cos(self._slam_heading_rad) * dt + nav_noise * 0.02
        self._slam_y_m += self._state.speed_mps * math.sin(self._slam_heading_rad) * dt - nav_noise * 0.02
        self._slam_heading_rad = _wrap_heading(self._slam_heading_rad + self._state.yaw_rate_rps * dt)

        lidar_support = (
            0.4 if self._sensor_enabled["lidar_front"] and self._sensor_health["lidar_front"] > 0.35 else 0.0
        )
        radar_support = (
            0.25 if self._sensor_enabled["radar_front"] and self._sensor_health["radar_front"] > 0.35 else 0.0
        )
        correction = lidar_support + radar_support
        self._slam_x_m += correction * (self._state.x_m - self._slam_x_m) * 0.08
        self._slam_y_m += correction * (self._state.y_m - self._slam_y_m) * 0.08
        self._state.slam_quality = _clamp(self._state.slam_quality - (0.015 - correction * 0.01), 0.2, 0.99)

    def _fuse_sensors(self) -> dict[str, Any]:
        gps_noise = self._rng.uniform(-1.5, 1.5)
        imu_noise = self._rng.uniform(-0.008, 0.008)
        wheel_noise = self._rng.uniform(-0.12, 0.12)
        lidar_noise = self._rng.uniform(-1.8, 1.8)
        radar_noise = self._rng.uniform(-2.2, 2.2)
        acoustic_noise = self._rng.uniform(-3.0, 3.0)
        thermal_noise = self._rng.uniform(-2.0, 2.0)
        camera_conf_noise = self._rng.uniform(-0.08, 0.08)

        lidar_distance = _clamp(120.0 - 1.1 * self._state.speed_mps + lidar_noise, 4.0, 200.0)
        radar_distance = _clamp(130.0 - 0.9 * self._state.speed_mps + radar_noise, 3.0, 220.0)
        camera_distance = _clamp(95.0 - 0.5 * self._state.speed_mps + lidar_noise * 0.5, 2.0, 150.0)

        if not self._sensor_enabled["lidar_front"] or self._sensor_health["lidar_front"] < 0.3:
            lidar_distance = 999.0
        if not self._sensor_enabled["radar_front"] or self._sensor_health["radar_front"] < 0.3:
            radar_distance = 999.0

        weights = [
            0.45 if lidar_distance < 900.0 else 0.0,
            0.35 if radar_distance < 900.0 else 0.0,
            0.20 if self._sensor_enabled["camera_day"] and self._sensor_health["camera_day"] > 0.35 else 0.0,
        ]
        weighted_dist = [lidar_distance, radar_distance, camera_distance]
        weight_total = sum(weights) if sum(weights) > 0.0 else 1.0
        self._state.obstacle_distance_m = sum(w * d for w, d in zip(weights, weighted_dist)) / weight_total

        gps_x = None
        gps_y = None
        if self._state.gps_available and self._sensor_enabled["gps"] and self._sensor_health["gps"] > 0.3:
            gps_x = self._state.x_m + gps_noise
            gps_y = self._state.y_m - gps_noise

        fused_x = self._slam_x_m
        fused_y = self._slam_y_m
        if gps_x is not None and gps_y is not None:
            fused_x = 0.6 * gps_x + 0.4 * self._slam_x_m
            fused_y = 0.6 * gps_y + 0.4 * self._slam_y_m

        return {
            "fused_pose": {
                "x_m": round(fused_x, 3),
                "y_m": round(fused_y, 3),
                "heading_rad": round(self._slam_heading_rad + imu_noise, 4),
            },
            "obstacle_distance_m": round(self._state.obstacle_distance_m, 3),
            "perception": {
                "camera_confidence": round(
                    _clamp(0.85 * self._sensor_health["camera_day"] + camera_conf_noise, 0.0, 1.0), 3
                ),
                "thermal_hotspot_c": round(33.0 + thermal_noise + 0.1 * self._state.engine_temp_c, 3),
                "acoustic_db": round(58.0 + 2.5 * self._state.speed_mps + acoustic_noise, 3),
                "lidar_range_m": round(lidar_distance, 3),
                "radar_range_m": round(radar_distance, 3),
            },
            "navigation": {
                "imu_heading_rad": round(self._state.heading_rad + imu_noise, 4),
                "wheel_speed_mps": round(self._state.speed_mps + wheel_noise, 3),
                "gps_x_m": None if gps_x is None else round(gps_x, 3),
                "gps_y_m": None if gps_y is None else round(gps_y, 3),
            },
            "sensor_health": {k: round(v, 3) for k, v in self._sensor_health.items()},
        }

    def _evaluate_degraded_mode(self) -> None:
        healthy_count = sum(
            1
            for name in self.SENSOR_NAMES
            if self._sensor_enabled[name] and self._sensor_health[name] >= 0.35
        )

        if not self._state.comms_available:
            self._enter_degraded_mode(reason="comms_loss", fallback_level=1)
            return
        if self._state.fuel_l < 4.0:
            self._enter_degraded_mode(reason="critical_fuel", fallback_level=0)
            return
        if self._state.engine_temp_c > 108.0:
            self._enter_degraded_mode(reason="thermal_warning", fallback_level=1)
            return
        if healthy_count <= 4:
            self._enter_degraded_mode(reason="sensor_dropout", fallback_level=1)
            return
        if (not self._state.gps_available) and self._state.slam_quality < 0.42:
            self._enter_degraded_mode(reason="gps_denied_low_slam_confidence", fallback_level=1)
            return

        self._state.degraded_mode = False
        self._state.degraded_reason = None

    def _enter_degraded_mode(self, reason: str, fallback_level: int) -> None:
        self._state.degraded_mode = True
        self._state.degraded_reason = reason
        self._state.autonomy_level = min(self._state.autonomy_level, fallback_level)
