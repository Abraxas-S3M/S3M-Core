"""VINS-Fusion adapter for GPS-denied tactical localization."""

from __future__ import annotations

import csv
import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.navigation.models import Pose

LOGGER = logging.getLogger(__name__)


def _quat_to_euler(qx: float, qy: float, qz: float, qw: float) -> tuple[float, float, float]:
    sinr_cosp = 2.0 * (qw * qx + qy * qz)
    cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
    roll = math.atan2(sinr_cosp, cosr_cosp)

    sinp = 2.0 * (qw * qy - qz * qx)
    if abs(sinp) >= 1.0:
        pitch = math.copysign(math.pi / 2.0, sinp)
    else:
        pitch = math.asin(sinp)

    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return (roll, pitch, yaw)


class VINSAdapter:
    """Adapter wrapper around ROS2 VINS odometry for contested navigation."""

    def __init__(self, topic: str = "/vins_estimator/odometry") -> None:
        self.topic = topic
        self._available = False
        self._connected = False
        self._latest_pose: Optional[Pose] = None
        self._messages_received = 0
        self._first_message_time: Optional[float] = None
        self._last_message_time: Optional[float] = None
        self._last_latency_ms: float = 0.0

        self._ros_node = None
        self._subscription = None
        self._rclpy = None
        self._qos = None
        self._odometry_type = None

    def connect(self) -> bool:
        try:
            import rclpy  # type: ignore
            from nav_msgs.msg import Odometry  # type: ignore
            from rclpy.qos import QoSProfile  # type: ignore
        except Exception:
            LOGGER.warning("rclpy unavailable — VINS adapter in offline mode")
            self._available = False
            self._connected = False
            return False

        try:
            self._rclpy = rclpy
            self._odometry_type = Odometry
            self._qos = QoSProfile(depth=10)
            if not rclpy.ok():
                rclpy.init(args=None)
            self._ros_node = rclpy.create_node("s3m_vins_adapter")
            self._subscription = self._ros_node.create_subscription(
                Odometry,
                self.topic,
                self._on_msg,
                self._qos,
            )
            self._available = True
            self._connected = True
            return True
        except Exception as exc:
            LOGGER.warning("Failed to connect VINS adapter: %s", exc)
            self._available = False
            self._connected = False
            return False

    def _on_msg(self, msg: Any) -> None:
        now = time.time()
        self._messages_received += 1
        if self._first_message_time is None:
            self._first_message_time = now
        self._last_message_time = now

        try:
            stamp = msg.header.stamp
            sec = float(getattr(stamp, "sec", 0))
            nanosec = float(getattr(stamp, "nanosec", 0))
            msg_time = sec + (nanosec / 1e9)
            if msg_time > 0:
                self._last_latency_ms = max(0.0, (now - msg_time) * 1000.0)
        except Exception:
            self._last_latency_ms = 0.0

        try:
            p = msg.pose.pose.position
            q = msg.pose.pose.orientation
            t = msg.twist.twist
            orientation = _quat_to_euler(float(q.x), float(q.y), float(q.z), float(q.w))
            self._latest_pose = Pose(
                position=(float(p.x), float(p.y), float(p.z)),
                orientation=orientation,
                velocity=(float(t.linear.x), float(t.linear.y), float(t.linear.z)),
                angular_velocity=(float(t.angular.x), float(t.angular.y), float(t.angular.z)),
                timestamp=datetime.now(timezone.utc),
                confidence=0.85,
                source="vio",
                covariance=None,
            )
        except Exception as exc:
            LOGGER.debug("Invalid VINS odometry message: %s", exc)

    def get_latest_pose(self) -> Optional[Pose]:
        if self._connected and self._rclpy and self._ros_node:
            try:
                self._rclpy.spin_once(self._ros_node, timeout_sec=0.0)
            except Exception:
                pass
        return self._latest_pose

    def is_available(self) -> bool:
        return self._available

    def get_stats(self) -> Dict[str, Any]:
        frequency = 0.0
        if self._messages_received > 1 and self._first_message_time and self._last_message_time:
            elapsed = max(1e-9, self._last_message_time - self._first_message_time)
            frequency = self._messages_received / elapsed
        return {
            "topic": self.topic,
            "available": self._available,
            "connected": self._connected,
            "messages_received": self._messages_received,
            "frequency_hz": frequency,
            "latency_ms": self._last_latency_ms,
        }

    def load_from_file(self, filepath: str) -> List[Pose]:
        if not isinstance(filepath, str) or not filepath.strip():
            raise ValueError("filepath must be a non-empty string")
        if not os.path.exists(filepath):
            raise FileNotFoundError(filepath)

        poses: List[Pose] = []
        with open(filepath, "r", encoding="utf-8") as handle:
            reader = csv.reader(handle, delimiter=" ")
            for raw in reader:
                row = [token for token in raw if token.strip()]
                if not row:
                    continue
                if row[0].startswith("#"):
                    continue
                if len(row) == 1 and "," in row[0]:
                    row = [x.strip() for x in row[0].split(",") if x.strip()]
                if len(row) < 8:
                    continue
                timestamp = float(row[0])
                px, py, pz = float(row[1]), float(row[2]), float(row[3])
                qx, qy, qz, qw = float(row[4]), float(row[5]), float(row[6]), float(row[7])
                roll, pitch, yaw = _quat_to_euler(qx, qy, qz, qw)
                poses.append(
                    Pose(
                        position=(px, py, pz),
                        orientation=(roll, pitch, yaw),
                        velocity=(0.0, 0.0, 0.0),
                        angular_velocity=(0.0, 0.0, 0.0),
                        timestamp=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                        confidence=0.8,
                        source="vio",
                        covariance=None,
                    )
                )
        return poses
