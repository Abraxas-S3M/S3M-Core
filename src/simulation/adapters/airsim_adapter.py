"""AirSim adapter with safe behavior when package is unavailable."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
import logging

from src.simulation.adapters.base_adapter import GenericSimAdapter
from src.simulation.models import EntityType, ScenarioDefinition, SimConfig, SimEntity, SimulationState, SimulatorStatus

LOGGER = logging.getLogger(__name__)


class AirSimAdapter(GenericSimAdapter):
    """Adapter for AirSim multirotor simulation integration."""

    def __init__(self, config: SimConfig) -> None:
        config.host = config.host or "localhost"
        if config.port == 0:
            config.port = 41451
        super().__init__(config)
        self._status = SimulatorStatus.DISCONNECTED
        self._connected = False
        self._available = False
        self._airsim = None
        self._client = None
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
            metadata={"simulator": "airsim", "tick_count": self._tick_count},
        )

    def connect(self) -> bool:
        try:
            import airsim  # type: ignore

            self._airsim = airsim
            self._client = airsim.MultirotorClient(ip=self.config.host)
            self._client.confirmConnection()
            self._client.enableApiControl(True)
            self._available = True
            self._connected = True
            self._status = SimulatorStatus.CONNECTED
            return True
        except ImportError:
            LOGGER.warning("airsim package not installed — AirSim adapter unavailable")
            self._available = False
            self._connected = False
            self._status = SimulatorStatus.ERROR
            return False
        except Exception as exc:
            LOGGER.error("AirSim connect failed: %s", exc)
            self._available = False
            self._connected = False
            self._status = SimulatorStatus.ERROR
            return False

    def disconnect(self) -> None:
        self._connected = False
        self._status = SimulatorStatus.DISCONNECTED

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

    def _collect_state(self) -> SimulationState:
        if not self.is_connected() or self._client is None:
            return self._last_state
        entities: list[SimEntity] = []
        try:
            names = []
            if hasattr(self._client, "listVehicles"):
                names = list(self._client.listVehicles())
            if not names:
                names = [""]
            for name in names:
                raw_state = self._client.getMultirotorState(vehicle_name=name)
                kin = raw_state.kinematics_estimated
                entity_id = name if name else "airsim-primary"
                entities.append(
                    SimEntity(
                        entity_id=entity_id,
                        entity_type=EntityType.FRIENDLY_UAV,
                        position=(kin.position.x_val, kin.position.y_val, kin.position.z_val),
                        velocity=(kin.linear_velocity.x_val, kin.linear_velocity.y_val, kin.linear_velocity.z_val),
                        heading=0.0,
                        health=1.0,
                        active=True,
                        metadata={"source": "airsim"},
                    )
                )
        except Exception as exc:
            LOGGER.error("AirSim state collection failed: %s", exc)
        return SimulationState(
            timestamp=datetime.now(timezone.utc),
            sim_time_seconds=self._sim_time,
            entities=entities,
            terrain={},
            weather={},
            active_events=[],
            metadata={"simulator": "airsim", "tick_count": self._tick_count},
        )

    def step(self, dt: float = 0.1) -> SimulationState:
        if not self.is_connected() or self._client is None:
            return self._last_state
        try:
            self._client.simContinueForTime(float(dt))
        except Exception:
            pass
        self._sim_time += max(0.0, float(dt))
        self._tick_count += 1
        self._status = SimulatorStatus.RUNNING
        self._last_state = self._collect_state()
        return self._last_state

    def get_state(self) -> SimulationState:
        self._last_state = self._collect_state()
        return self._last_state

    def spawn_entity(
        self,
        entity_type: EntityType,
        position: Tuple[float, float, float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not self.is_connected() or self._client is None:
            return ""
        entity_id = f"airsim-{entity_type.value.lower()}-{self._tick_count}"
        try:
            if entity_type in {EntityType.FRIENDLY_UAV, EntityType.ENEMY_UAV} and hasattr(self._client, "simAddVehicle"):
                self._client.simAddVehicle(entity_id, "SimpleFlight", self._airsim.Pose())
            elif hasattr(self._client, "simSpawnObject"):
                self._client.simSpawnObject(entity_id, "Cube", self._airsim.Pose(), 1.0)
        except Exception:
            pass
        return entity_id

    def remove_entity(self, entity_id: str) -> None:
        return None

    def set_entity_target(self, entity_id: str, target_position: tuple, speed: float = 10.0) -> None:
        if not self.is_connected() or self._client is None:
            return
        try:
            self._client.moveToPositionAsync(
                target_position[0],
                target_position[1],
                target_position[2],
                float(speed),
                vehicle_name=entity_id,
            )
        except Exception:
            return

    def load_scenario(self, scenario: ScenarioDefinition) -> bool:
        return self.is_connected()

    def get_sim_time(self) -> float:
        return self._sim_time

    def capture_image(self, camera_name: str = "front_center") -> Optional[bytes]:
        """Capture tactical image frames for ATR synthetic dataset generation."""
        if not self.is_connected() or self._client is None or self._airsim is None:
            return None
        try:
            image = self._client.simGetImage(camera_name, self._airsim.ImageType.Scene)
            if isinstance(image, bytes):
                return image
            if isinstance(image, str):
                return image.encode("latin1", errors="ignore")
        except Exception:
            return None
        return None

    def health_check(self) -> dict:
        return {
            "adapter": "airsim",
            "available": self._available,
            "connected": self._connected,
            "status": self._status.value,
        }
