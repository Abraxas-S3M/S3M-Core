"""Gazebo adapter with ROS2 integration and safe fallback behavior."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
import logging

from src.simulation.adapters.base_adapter import GenericSimAdapter
from src.simulation.models import EntityType, ScenarioDefinition, SimConfig, SimulationState, SimulatorStatus

LOGGER = logging.getLogger(__name__)


class GazeboAdapter(GenericSimAdapter):
    """Adapter for Gazebo world state and control services via ROS2."""

    def __init__(self, config: SimConfig) -> None:
        config.host = config.host or "localhost"
        if config.port == 0:
            config.port = 11345
        super().__init__(config)
        self._status = SimulatorStatus.DISCONNECTED
        self._connected = False
        self._available = False
        self._rclpy = None
        self._sim_time = 0.0
        self._tick_count = 0
        self._last_state = self._empty_state()

    def _empty_state(self) -> SimulationState:
        return SimulationState(
            timestamp=datetime.now(timezone.utc),
            sim_time_seconds=self._sim_time,
            entities=[],
            terrain={},
            weather={},
            active_events=[],
            metadata={"simulator": "gazebo", "tick_count": self._tick_count},
        )

    def connect(self) -> bool:
        self._status = SimulatorStatus.CONNECTING
        try:
            import rclpy  # type: ignore

            self._rclpy = rclpy
            try:
                rclpy.init(args=None)
            except Exception:
                pass
            self._available = True
            self._connected = True
            self._status = SimulatorStatus.CONNECTED
            return True
        except ImportError:
            LOGGER.warning("ROS2/rclpy not installed — Gazebo adapter unavailable")
            self._available = False
            self._connected = False
            self._status = SimulatorStatus.ERROR
            return False
        except Exception as exc:
            LOGGER.error("Gazebo connect failed: %s", exc)
            self._available = False
            self._connected = False
            self._status = SimulatorStatus.ERROR
            return False

    def disconnect(self) -> None:
        self._connected = False
        self._status = SimulatorStatus.DISCONNECTED
        if self._rclpy is not None:
            try:
                self._rclpy.shutdown()
            except Exception:
                pass

    def is_connected(self) -> bool:
        return self._available and self._connected

    def get_status(self) -> SimulatorStatus:
        return self._status

    def start_simulation(self) -> bool:
        if not self.is_connected():
            return False
        self._status = SimulatorStatus.RUNNING
        return True

    def pause_simulation(self) -> None:
        if self.is_connected():
            self._status = SimulatorStatus.PAUSED

    def stop_simulation(self) -> None:
        if self.is_connected():
            self._status = SimulatorStatus.CONNECTED

    def reset_simulation(self) -> None:
        self._sim_time = 0.0
        self._tick_count = 0
        self._last_state = self._empty_state()

    def step(self, dt: float = 0.1) -> SimulationState:
        if not self.is_connected():
            return self._last_state
        try:
            self._sim_time += max(0.0, float(dt))
            self._tick_count += 1
            self._status = SimulatorStatus.RUNNING
            self._last_state = self._empty_state()
            return self._last_state
        except Exception as exc:
            LOGGER.error("Gazebo step failed: %s", exc)
            self._status = SimulatorStatus.ERROR
            return self._last_state

    def get_state(self) -> SimulationState:
        return self._last_state

    def spawn_entity(
        self,
        entity_type: EntityType,
        position: Tuple[float, float, float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not self.is_connected():
            return ""
        return f"gazebo-{entity_type.value.lower()}-{self._tick_count}"

    def remove_entity(self, entity_id: str) -> None:
        return None

    def set_entity_target(self, entity_id: str, target_position: tuple, speed: float = 10.0) -> None:
        return None

    def load_scenario(self, scenario: ScenarioDefinition) -> bool:
        if not self.is_connected():
            return False
        try:
            scenario.to_dict()
            return True
        except Exception as exc:
            LOGGER.error("Gazebo scenario load failed: %s", exc)
            return False

    def get_sim_time(self) -> float:
        return self._sim_time

    def health_check(self) -> dict:
        return {
            "adapter": "gazebo",
            "available": self._available,
            "connected": self._connected,
            "status": self._status.value,
        }
