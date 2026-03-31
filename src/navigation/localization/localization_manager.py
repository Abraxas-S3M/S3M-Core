"""Localization manager coordinating all Layer 05 position sources."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.navigation.localization.dead_reckoning import DeadReckoning
from src.navigation.localization.gps_monitor import GPSMonitor
from src.navigation.localization.lidar_odom_adapter import LidarOdomAdapter
from src.navigation.localization.pose_estimator import PoseEstimator
from src.navigation.localization.vins_adapter import VINSAdapter
from src.navigation.models import GPSQuality, GPSStatus, NavState, Pose


class LocalizationManager:
    """Fuses GPS, VIO, LiDAR odometry, and IMU for contested navigation."""

    def __init__(self) -> None:
        self.pose_estimator = PoseEstimator()
        self.vins_adapter = VINSAdapter()
        self.lidar_adapter = LidarOdomAdapter()
        self.dead_reckoning = DeadReckoning()
        self.gps_monitor = GPSMonitor()
        self.started = False
        self.mode_override: Optional[str] = None
        self.latest_state: Optional[NavState] = None
        self.pose_history: List[Pose] = []
        self.max_history = 500

    def start(self) -> None:
        self.vins_adapter.connect()
        self.lidar_adapter.connect()
        self.started = True

    def update(
        self,
        imu_data: Optional[Dict[str, Tuple[float, float, float]]] = None,
        gps_data: Optional[Dict[str, Any]] = None,
    ) -> NavState:
        active_sources: List[str] = []
        if gps_data:
            gps_status = self.gps_monitor.update(
                satellites=int(gps_data.get("satellites", 0)),
                hdop=float(gps_data.get("hdop", 99.0)),
                fix_type=str(gps_data.get("fix_type", "none")),
                position=gps_data.get("position"),
            )
            if gps_status.is_usable() and gps_status.position:
                self.pose_estimator.update_from_gps(
                    position=gps_status.position,
                    covariance=gps_data.get("covariance"),
                )
                active_sources.append("gps")
        else:
            gps_status = self.gps_monitor.current_status

        vins_pose = self.vins_adapter.get_latest_pose()
        if vins_pose:
            self.pose_estimator.update_from_vio(
                position=vins_pose.position,
                orientation=vins_pose.orientation,
                confidence=vins_pose.confidence,
            )
            active_sources.append("vio")

        lidar_pose = self.lidar_adapter.get_latest_pose()
        if lidar_pose:
            self.pose_estimator.update_from_lidar(
                position=lidar_pose.position,
                orientation=lidar_pose.orientation,
                confidence=lidar_pose.confidence,
            )
            active_sources.append("lidar_odom")

        if imu_data:
            linear_accel = imu_data.get("linear_accel", (0.0, 0.0, 0.0))
            angular_vel = imu_data.get("angular_vel", (0.0, 0.0, 0.0))
            dt = float(imu_data.get("dt", 0.05))
            self.pose_estimator.update_from_imu(linear_accel=linear_accel, angular_vel=angular_vel, dt=dt)
            dr_pose = self.dead_reckoning.update(linear_accel=linear_accel, angular_vel=angular_vel, dt=dt)
            active_sources.append("imu")
            if not any(src in active_sources for src in ("gps", "vio", "lidar_odom")):
                # Tactical fallback: when external aids are denied, use dead reckoning pose.
                fused_pose = dr_pose
            else:
                fused_pose = self.pose_estimator.get_pose()
                self.dead_reckoning.correct(fused_pose)
        else:
            fused_pose = self.pose_estimator.get_pose()

        if self.mode_override:
            mode = self.mode_override
        elif gps_status.is_usable():
            mode = "gps_fused"
        elif "vio" in active_sources:
            mode = "visual_inertial"
        elif "lidar_odom" in active_sources:
            mode = "lidar_inertial"
        else:
            mode = "dead_reckoning"

        if mode == "dead_reckoning":
            fused_pose = self.dead_reckoning.get_pose()
        elif mode in ("gps_fused", "visual_inertial", "lidar_inertial"):
            self.dead_reckoning.correct(fused_pose)

        self.pose_history.append(fused_pose)
        if len(self.pose_history) > self.max_history:
            self.pose_history.pop(0)

        state = NavState(
            pose=fused_pose,
            gps_status=gps_status,
            localization_mode=mode,
            active_sources=sorted(set(active_sources)),
            drift_estimate_meters=self.pose_estimator.get_drift_estimate(),
            last_update=datetime.now(timezone.utc),
        )
        self.latest_state = state
        return state

    def get_state(self) -> NavState:
        if self.latest_state is None:
            pose = self.pose_estimator.get_pose()
            self.latest_state = NavState(
                pose=pose,
                gps_status=self.gps_monitor.current_status,
                localization_mode=self.mode_override or "dead_reckoning",
                active_sources=[],
                drift_estimate_meters=self.pose_estimator.get_drift_estimate(),
                last_update=datetime.now(timezone.utc),
            )
        return self.latest_state

    def get_pose(self) -> Pose:
        return self.get_state().pose

    def get_pose_history(self, limit: int = 100) -> List[Pose]:
        if limit <= 0:
            return []
        return self.pose_history[-limit:]

    def reset(self, position: Tuple[float, float, float]) -> None:
        self.pose_estimator.reset(position)
        self.dead_reckoning.reset(position, (0.0, 0.0, 0.0))
        self.pose_history.clear()
        self.latest_state = None

    def force_mode(self, mode: str) -> None:
        allowed = {"gps_fused", "visual_inertial", "lidar_inertial", "dead_reckoning"}
        if mode not in allowed:
            raise ValueError(f"Unsupported mode override: {mode}")
        self.mode_override = mode

    def health_check(self) -> Dict[str, Any]:
        state = self.get_state()
        return {
            "started": self.started,
            "mode": state.localization_mode,
            "drift_meters": state.drift_estimate_meters,
            "gps_quality": state.gps_status.quality.value,
            "sources": {
                "gps": not state.gps_status.is_denied(),
                "vins": self.vins_adapter.is_available(),
                "lidar_odom": self.lidar_adapter.is_available(),
                "dead_reckoning": True,
            },
            "vins_stats": self.vins_adapter.get_stats(),
            "lidar_stats": self.lidar_adapter.get_stats(),
        }
