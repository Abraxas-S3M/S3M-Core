"""LiDAR odometry adapter with ROS2 and offline file fallback."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.navigation.models import Pose
from src.navigation.localization.vins_adapter import _quat_to_euler

LOGGER = logging.getLogger(__name__)


class LidarOdomAdapter:
    """Reads LiDAR-inertial pose streams for contested tactical navigation."""

    def __init__(self, topic: str = "/lio_sam/mapping/odometry") -> None:
        if not isinstance(topic, str) or not topic.strip():
            raise ValueError("topic must be a non-empty string")
        self.topic = topic.strip()
        self._available = False
        self._latest_pose: Optional[Pose] = None
        self._messages_received = 0
        self._connected_at: Optional[float] = None
        self._last_msg_time: Optional[float] = None
        self._latency_samples_ms: List[float] = []
        self._node = None
        self._subscription = None

    def connect(self) -> bool:
        try:
            import rclpy  # type: ignore
            from nav_msgs.msg import Odometry  # type: ignore
        except Exception:
            LOGGER.info("rclpy unavailable — LiDAR odom adapter in offline mode")
            self._available = False
            return False
        try:
            if not rclpy.ok():
                rclpy.init(args=None)
            self._node = rclpy.create_node("s3m_lidar_odom_adapter")
            self._subscription = self._node.create_subscription(
                Odometry,
                self.topic,
                self._on_message,
                10,
            )
            self._available = True
            self._connected_at = time.perf_counter()
            return True
        except Exception as exc:
            LOGGER.warning("Failed to initialize LiDAR odometry adapter: %s", exc)
            self._available = False
            return False

    def _on_message(self, msg: Any) -> None:
        try:
            stamp = getattr(getattr(msg, "header", None), "stamp", None)
            msg_ts = None
            if stamp is not None and hasattr(stamp, "sec") and hasattr(stamp, "nanosec"):
                msg_ts = float(stamp.sec) + float(stamp.nanosec) * 1e-9
            position = (
                float(msg.pose.pose.position.x),
                float(msg.pose.pose.position.y),
                float(msg.pose.pose.position.z),
            )
            q = msg.pose.pose.orientation
            orientation = _quat_to_euler(float(q.x), float(q.y), float(q.z), float(q.w))
            now = time.perf_counter()
            if msg_ts is not None:
                latency = max(0.0, time.time() - msg_ts) * 1000.0
                self._latency_samples_ms.append(latency)
                if len(self._latency_samples_ms) > 200:
                    self._latency_samples_ms = self._latency_samples_ms[-200:]
            self._latest_pose = Pose(
                position=position,
                orientation=orientation,
                velocity=(
                    float(msg.twist.twist.linear.x),
                    float(msg.twist.twist.linear.y),
                    float(msg.twist.twist.linear.z),
                ),
                angular_velocity=(
                    float(msg.twist.twist.angular.x),
                    float(msg.twist.twist.angular.y),
                    float(msg.twist.twist.angular.z),
                ),
                timestamp=datetime.now(timezone.utc),
                confidence=0.9,
                source="lidar_odom",
            )
            self._messages_received += 1
            self._last_msg_time = now
        except Exception as exc:
            LOGGER.debug("LiDAR odom message parse error: %s", exc)

    def get_latest_pose(self) -> Optional[Pose]:
        if self._available and self._node is not None:
            try:
                import rclpy  # type: ignore

                rclpy.spin_once(self._node, timeout_sec=0.0)
            except Exception:
                pass
        return self._latest_pose

    def is_available(self) -> bool:
        return self._available

    def get_stats(self) -> Dict[str, Any]:
        now = time.perf_counter()
        elapsed = 0.0 if self._connected_at is None else max(1e-6, now - self._connected_at)
        frequency = float(self._messages_received) / elapsed if elapsed > 0 else 0.0
        avg_latency = (
            sum(self._latency_samples_ms) / len(self._latency_samples_ms)
            if self._latency_samples_ms
            else 0.0
        )
        return {
            "topic": self.topic,
            "available": self._available,
            "messages_received": self._messages_received,
            "frequency_hz": frequency,
            "avg_latency_ms": avg_latency,
            "has_latest_pose": self._latest_pose is not None,
        }

    def load_from_file(self, filepath: str) -> List[Pose]:
        if not isinstance(filepath, str) or not filepath.strip():
            raise ValueError("filepath must be a non-empty string")
        poses: List[Pose] = []
        with open(filepath, "r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                parts = raw.replace(",", " ").split()
                if len(parts) < 8:
                    continue
                try:
                    timestamp_value = float(parts[0])
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    qx, qy, qz, qw = float(parts[4]), float(parts[5]), float(parts[6]), float(parts[7])
                    orientation = _quat_to_euler(qx, qy, qz, qw)
                    ts = datetime.fromtimestamp(timestamp_value, tz=timezone.utc)
                except Exception:
                    continue
                poses.append(
                    Pose(
                        position=(x, y, z),
                        orientation=orientation,
                        velocity=(0.0, 0.0, 0.0),
                        angular_velocity=(0.0, 0.0, 0.0),
                        timestamp=ts,
                        confidence=0.85,
                        source="lidar_odom",
                    )
                )
        return poses
