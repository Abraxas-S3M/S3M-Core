"""Pose estimator for contested navigation under tactical signal degradation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from math import sqrt
from typing import Dict, List, Optional, Tuple

from src.navigation.models import Pose
from src.sensor_fusion.ekf_filter import EKFFilter

LOGGER = logging.getLogger(__name__)

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None  # type: ignore


class PoseEstimator:
    """Fuses GPS, VIO, LiDAR odometry, and IMU for resilient tactical pose.

    Military context:
    When adversaries jam or spoof GNSS, this estimator maintains continuity
    by weighting trusted local sensors and inertial dead reckoning.
    """

    def __init__(self, dt: float = 0.05) -> None:
        if not isinstance(dt, (int, float)) or dt <= 0:
            raise ValueError("dt must be a positive number")
        self.dt = float(dt)
        self.ekf = EKFFilter(dt=self.dt, process_noise=1.0, measurement_noise=0.5)
        self.source_weights: Dict[str, float] = {
            "gps": 1.0,
            "vio": 0.8,
            "lidar_odom": 0.9,
            "imu": 0.3,
        }
        self._orientation = (0.0, 0.0, 0.0)
        self._angular_velocity = (0.0, 0.0, 0.0)
        self._last_pose: Optional[Pose] = None
        self._prediction_only_position = (0.0, 0.0, 0.0)
        self._drift_estimate = 0.0
        self._last_update_sources: List[str] = []
        self._imu_updates = 0
        self._numpy_available = np is not None
        if not self._numpy_available:
            LOGGER.warning("NumPy unavailable — PoseEstimator using reduced precision math fallback")

    def _validate_position(self, position: Tuple[float, float, float]) -> Tuple[float, float, float]:
        if not isinstance(position, tuple) or len(position) != 3:
            raise ValueError("position must be a tuple of (x, y, z)")
        if not all(isinstance(v, (int, float)) for v in position):
            raise ValueError("position must contain numeric values")
        return (float(position[0]), float(position[1]), float(position[2]))

    def _validate_orientation(self, orientation: Tuple[float, float, float]) -> Tuple[float, float, float]:
        if not isinstance(orientation, tuple) or len(orientation) != 3:
            raise ValueError("orientation must be a tuple of (roll, pitch, yaw)")
        if not all(isinstance(v, (int, float)) for v in orientation):
            raise ValueError("orientation must contain numeric values")
        return (float(orientation[0]), float(orientation[1]), float(orientation[2]))

    def _record_source(self, source: str) -> None:
        if source not in self._last_update_sources:
            self._last_update_sources.append(source)

    def _weighted_measurement(
        self,
        measurement: Tuple[float, float, float],
        source: str,
    ) -> Tuple[float, float, float]:
        base_state = self.ekf.get_state()
        current = base_state["position"]
        weight = self.source_weights.get(source, 0.5)
        if self._numpy_available:
            cur = np.asarray(current, dtype=float)  # type: ignore[union-attr]
            meas = np.asarray(measurement, dtype=float)  # type: ignore[union-attr]
            fused = (cur * (1.0 - weight)) + (meas * weight)
            return (float(fused[0]), float(fused[1]), float(fused[2]))
        return (
            (current[0] * (1.0 - weight)) + (measurement[0] * weight),
            (current[1] * (1.0 - weight)) + (measurement[1] * weight),
            (current[2] * (1.0 - weight)) + (measurement[2] * weight),
        )

    def update_from_gps(
        self,
        position: Tuple[float, float, float],
        covariance: Optional[List[List[float]]] = None,
    ) -> None:
        """Fuse GPS measurement with EKF using source-trust weighting."""
        pos = self._validate_position(position)
        self.ekf.predict()
        weighted = self._weighted_measurement(pos, "gps")
        self.ekf.update(weighted)
        if covariance and hasattr(self.ekf, "R"):
            try:
                if self._numpy_available:
                    self.ekf.R = np.asarray(covariance, dtype=float)  # type: ignore[assignment, union-attr]
            except Exception as exc:  # pragma: no cover
                LOGGER.debug("Unable to apply provided covariance: %s", exc)
        self._record_source("gps")

    def update_from_vio(
        self,
        position: Tuple[float, float, float],
        orientation: Tuple[float, float, float],
        confidence: float,
    ) -> None:
        """Fuse visual-inertial pose estimate for GPS-denied maneuvering."""
        pos = self._validate_position(position)
        self._orientation = self._validate_orientation(orientation)
        conf = max(0.0, min(1.0, float(confidence)))
        self.set_source_weight("vio", conf)
        self.ekf.predict()
        self.ekf.update(self._weighted_measurement(pos, "vio"))
        self._record_source("vio")

    def update_from_lidar(
        self,
        position: Tuple[float, float, float],
        orientation: Tuple[float, float, float],
        confidence: float,
    ) -> None:
        """Fuse LiDAR odometry for robust localization in visual obscurants."""
        pos = self._validate_position(position)
        self._orientation = self._validate_orientation(orientation)
        conf = max(0.0, min(1.0, float(confidence)))
        self.set_source_weight("lidar_odom", conf)
        self.ekf.predict()
        self.ekf.update(self._weighted_measurement(pos, "lidar_odom"))
        self._record_source("lidar_odom")

    def update_from_imu(
        self,
        linear_accel: Tuple[float, float, float],
        angular_vel: Tuple[float, float, float],
        dt: float,
    ) -> None:
        """Predict state with IMU dead reckoning when external fixes are absent."""
        accel = self._validate_position(linear_accel)
        self._angular_velocity = self._validate_orientation(angular_vel)
        if not isinstance(dt, (int, float)) or dt <= 0:
            raise ValueError("dt must be a positive number")
        delta_t = float(dt)
        self.ekf.predict()
        state = self.ekf.get_state()
        vx, vy, vz = state["velocity"]
        vx += accel[0] * delta_t
        vy += accel[1] * delta_t
        vz += accel[2] * delta_t
        px, py, pz = state["position"]
        pred = (
            px + (vx * delta_t),
            py + (vy * delta_t),
            pz + (vz * delta_t),
        )
        self._prediction_only_position = pred
        # Bias toward prediction for contested conditions without fully replacing EKF.
        imu_weight = self.source_weights.get("imu", 0.3)
        self.ekf.update(
            (
                px * (1.0 - imu_weight) + pred[0] * imu_weight,
                py * (1.0 - imu_weight) + pred[1] * imu_weight,
                pz * (1.0 - imu_weight) + pred[2] * imu_weight,
            )
        )
        self._imu_updates += 1
        self._record_source("imu")

    def get_pose(self) -> Pose:
        state = self.ekf.get_state()
        position = (
            float(state["position"][0]),
            float(state["position"][1]),
            float(state["position"][2]),
        )
        velocity = (
            float(state["velocity"][0]),
            float(state["velocity"][1]),
            float(state["velocity"][2]),
        )
        covariance = state.get("covariance")
        confidence = max(0.0, min(1.0, 1.0 - min(self._drift_estimate / 500.0, 0.7)))
        if self._imu_updates > 0 and len(self._last_update_sources) == 1 and self._last_update_sources[0] == "imu":
            confidence = max(0.2, confidence - min(0.3, self._imu_updates * 0.001))
        source = "fused" if self._last_update_sources else "dead_reckoning"
        pose = Pose(
            position=position,
            orientation=self._orientation,
            velocity=velocity,
            angular_velocity=self._angular_velocity,
            timestamp=datetime.now(timezone.utc),
            confidence=confidence,
            source=source,
            covariance=covariance if isinstance(covariance, list) else None,
        )
        self._last_pose = pose
        # Reset source tracker after snapshot so each cycle reports fresh contributors.
        self._last_update_sources = []
        return pose

    def get_drift_estimate(self) -> float:
        if self._last_pose is None:
            return self._drift_estimate
        dx = self._prediction_only_position[0] - self._last_pose.position[0]
        dy = self._prediction_only_position[1] - self._last_pose.position[1]
        dz = self._prediction_only_position[2] - self._last_pose.position[2]
        instant = sqrt(dx * dx + dy * dy + dz * dz)
        self._drift_estimate = max(self._drift_estimate, instant)
        return self._drift_estimate

    def reset(self, initial_position: Tuple[float, float, float] = (0.0, 0.0, 0.0)) -> None:
        pos = self._validate_position(initial_position)
        self.ekf.reset(initial_state=[pos[0], pos[1], pos[2], 0.0, 0.0, 0.0])
        self._orientation = (0.0, 0.0, 0.0)
        self._angular_velocity = (0.0, 0.0, 0.0)
        self._prediction_only_position = pos
        self._drift_estimate = 0.0
        self._imu_updates = 0
        self._last_pose = None
        self._last_update_sources = []

    def set_source_weight(self, source: str, weight: float) -> None:
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source must be a non-empty string")
        if not isinstance(weight, (int, float)) or not (0.0 <= float(weight) <= 1.0):
            raise ValueError("weight must be in [0, 1]")
        self.source_weights[source.strip().lower()] = float(weight)

    def get_source_weights(self) -> Dict[str, float]:
        return dict(self.source_weights)
