"""Base adapter contract and built-in tactical fallback simulator."""

from __future__ import annotations

from datetime import datetime, timezone
from math import atan2, degrees, sqrt
from typing import Any, Dict
from uuid import uuid4

from src.simulation.models import (
    EntityType,
    ScenarioDefinition,
    SimConfig,
    SimEntity,
    SimulationState,
    SimulatorStatus,
)


class GenericSimAdapter:
    """Abstract interface implemented by every external simulator adapter."""

    def __init__(self, config: SimConfig) -> None:
        if not isinstance(config, SimConfig):
            raise ValueError("config must be SimConfig")
        self.config = config

    def connect(self) -> bool:
        raise NotImplementedError

    def disconnect(self) -> None:
        raise NotImplementedError

    def is_connected(self) -> bool:
        raise NotImplementedError

    def get_status(self) -> SimulatorStatus:
        raise NotImplementedError

    def start_simulation(self) -> bool:
        raise NotImplementedError

    def pause_simulation(self) -> None:
        raise NotImplementedError

    def stop_simulation(self) -> None:
        raise NotImplementedError

    def reset_simulation(self) -> None:
        raise NotImplementedError

    def step(self, dt: float = 0.1) -> SimulationState:
        raise NotImplementedError

    def get_state(self) -> SimulationState:
        raise NotImplementedError

    def spawn_entity(
        self,
        entity_type: EntityType,
        position: tuple,
        metadata: dict | None = None,
    ) -> str:
        raise NotImplementedError

    def remove_entity(self, entity_id: str) -> None:
        raise NotImplementedError

    def set_entity_target(self, entity_id: str, target_position: tuple, speed: float = 10.0) -> None:
        raise NotImplementedError

    def load_scenario(self, scenario: ScenarioDefinition) -> bool:
        raise NotImplementedError

    def get_sim_time(self) -> float:
        raise NotImplementedError

    def health_check(self) -> dict:
        raise NotImplementedError


class BuiltinPhysicsEngine(GenericSimAdapter):
    """Zero-dependency simulator for tactical logic validation on edge devices.

    This engine intentionally uses simplified kinematics so field teams can still
    rehearse mission logic when high-fidelity simulators are unavailable.
    """

    def __init__(self, config: SimConfig) -> None:
        super().__init__(config)
        self._status = SimulatorStatus.DISCONNECTED
        self._connected = False
        self._running = False
        self._entities: Dict[str, SimEntity] = {}
        self._targets: Dict[str, Dict[str, Any]] = {}
        self._sim_time = 0.0
        self._tick_count = 0
        self._terrain = {
            "bounds": [[0.0, 0.0, 0.0], [1000.0, 1000.0, 200.0]],
            "obstacles": [],
            "type": "training_range",
        }
        self._weather = {
            "visibility": 1.0,
            "wind_speed": 0.0,
            "wind_direction": 0.0,
            "precipitation": "none",
        }
        self._active_events: list[dict] = []
        self._max_entities = min(200, int(config.extra_params.get("max_entities", 200)))

    def _state(self) -> SimulationState:
        return SimulationState(
            timestamp=datetime.now(timezone.utc),
            sim_time_seconds=self._sim_time,
            entities=list(self._entities.values()),
            terrain=dict(self._terrain),
            weather=dict(self._weather),
            active_events=list(self._active_events[-500:]),
            metadata={
                "simulator": self.config.simulator_name,
                "tick_count": self._tick_count,
                "real_time_ratio": self.config.real_time_factor,
            },
        )

    def connect(self) -> bool:
        self._status = SimulatorStatus.CONNECTING
        self._connected = True
        self._status = SimulatorStatus.CONNECTED
        return True

    def disconnect(self) -> None:
        self._connected = False
        self._running = False
        self._status = SimulatorStatus.DISCONNECTED

    def is_connected(self) -> bool:
        return self._connected

    def get_status(self) -> SimulatorStatus:
        return self._status

    def start_simulation(self) -> bool:
        if not self._connected:
            return False
        self._running = True
        self._status = SimulatorStatus.RUNNING
        return True

    def pause_simulation(self) -> None:
        if self._connected:
            self._running = False
            self._status = SimulatorStatus.PAUSED

    def stop_simulation(self) -> None:
        self._running = False
        if self._connected:
            self._status = SimulatorStatus.CONNECTED

    def reset_simulation(self) -> None:
        self._entities.clear()
        self._targets.clear()
        self._active_events.clear()
        self._sim_time = 0.0
        self._tick_count = 0

    def _friendly(self, entity: SimEntity) -> bool:
        return entity.entity_type.value.startswith("FRIENDLY_")

    def _move_entity(self, entity: SimEntity, target: tuple[float, float, float], speed: float, dt: float) -> None:
        dx = target[0] - entity.position[0]
        dy = target[1] - entity.position[1]
        dz = target[2] - entity.position[2]
        distance = sqrt(dx * dx + dy * dy + dz * dz)
        if distance < 1e-9:
            entity.velocity = (0.0, 0.0, 0.0)
            return

        step = min(speed * dt, distance)
        ux, uy, uz = dx / distance, dy / distance, dz / distance
        entity.position = (
            entity.position[0] + ux * step,
            entity.position[1] + uy * step,
            entity.position[2] + uz * step,
        )
        entity.velocity = (ux * speed, uy * speed, uz * speed)
        entity.heading = (degrees(atan2(uy, ux)) + 360.0) % 360.0

    def _collision_phase(self) -> None:
        ids = list(self._entities.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a = self._entities[ids[i]]
                b = self._entities[ids[j]]
                if a.distance_to(b) > 5.0:
                    continue
                if self._friendly(a) == self._friendly(b):
                    continue
                a.health = max(0.0, a.health - 0.25)
                b.health = max(0.0, b.health - 0.25)
                self._active_events.append(
                    {
                        "type": "engagement_started",
                        "sim_time_seconds": self._sim_time,
                        "entities": [a.entity_id, b.entity_id],
                        "damage": 0.25,
                    }
                )

    def _cleanup_destroyed(self) -> None:
        for entity_id, entity in list(self._entities.items()):
            if entity.health > 0.0:
                continue
            entity.active = False
            self._active_events.append(
                {
                    "type": "entity_killed",
                    "sim_time_seconds": self._sim_time,
                    "entity_id": entity_id,
                    "entity_type": entity.entity_type.value,
                }
            )
            self._entities.pop(entity_id, None)
            self._targets.pop(entity_id, None)

    def step(self, dt: float = 0.1) -> SimulationState:
        if not isinstance(dt, (int, float)) or float(dt) <= 0:
            raise ValueError("dt must be a positive number")
        dt = float(dt)
        if not self._connected:
            self._status = SimulatorStatus.ERROR
            return self._state()

        if self._running:
            for entity_id, target_data in list(self._targets.items()):
                entity = self._entities.get(entity_id)
                if entity is None:
                    continue
                self._move_entity(entity, target_data["target"], target_data["speed"], dt)

            self._collision_phase()
            self._cleanup_destroyed()
            self._sim_time += dt
            self._tick_count += 1

        return self._state()

    def get_state(self) -> SimulationState:
        return self._state()

    def spawn_entity(
        self,
        entity_type: EntityType,
        position: tuple,
        metadata: dict | None = None,
    ) -> str:
        if not self._connected:
            raise RuntimeError("adapter not connected")
        if len(self._entities) >= self._max_entities:
            raise ValueError("max entity limit reached (200)")
        if not isinstance(entity_type, EntityType):
            entity_type = EntityType(str(entity_type))
        if isinstance(position, list):
            position = tuple(position)
        if not isinstance(position, tuple) or len(position) != 3:
            raise ValueError("position must be a length-3 tuple/list")

        entity_id = str(uuid4())
        self._entities[entity_id] = SimEntity(
            entity_id=entity_id,
            entity_type=entity_type,
            position=(float(position[0]), float(position[1]), float(position[2])),
            velocity=(0.0, 0.0, 0.0),
            heading=0.0,
            health=1.0,
            active=True,
            metadata=dict(metadata or {}),
        )
        self._active_events.append(
            {
                "type": "spawn",
                "sim_time_seconds": self._sim_time,
                "entity_id": entity_id,
                "entity_type": entity_type.value,
            }
        )
        return entity_id

    def remove_entity(self, entity_id: str) -> None:
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError("entity_id must be a non-empty string")
        self._entities.pop(entity_id, None)
        self._targets.pop(entity_id, None)

    def set_entity_target(self, entity_id: str, target_position: tuple, speed: float = 10.0) -> None:
        if entity_id not in self._entities:
            return
        if isinstance(target_position, list):
            target_position = tuple(target_position)
        if not isinstance(target_position, tuple) or len(target_position) != 3:
            raise ValueError("target_position must be a length-3 tuple/list")
        if not isinstance(speed, (int, float)) or float(speed) <= 0:
            raise ValueError("speed must be positive")
        self._targets[entity_id] = {
            "target": (float(target_position[0]), float(target_position[1]), float(target_position[2])),
            "speed": float(speed),
        }

    def load_scenario(self, scenario: ScenarioDefinition) -> bool:
        if not isinstance(scenario, ScenarioDefinition):
            raise ValueError("scenario must be ScenarioDefinition")
        if not self._connected:
            return False

        ok, errors = scenario.validate()
        if not ok:
            raise ValueError(f"invalid scenario: {errors}")

        self.reset_simulation()
        self._terrain = dict(scenario.terrain)
        self._weather = dict(scenario.weather)

        for force in scenario.forces:
            for unit in force.units:
                base = unit["starting_position"]
                for idx in range(unit["count"]):
                    # Tactical spacing avoids immediate blue-on-blue or red-on-red collisions.
                    offset = (float((idx % 5) * 3.0), float((idx // 5) * 3.0), 0.0)
                    self.spawn_entity(
                        entity_type=unit["type"],
                        position=(base[0] + offset[0], base[1] + offset[1], base[2] + offset[2]),
                        metadata={
                            "force_name": force.force_name,
                            "allegiance": force.allegiance,
                            "behavior": unit["behavior"],
                        },
                    )
        return True

    def get_sim_time(self) -> float:
        return self._sim_time

    def health_check(self) -> dict:
        return {
            "adapter": "builtin",
            "connected": self._connected,
            "running": self._running,
            "status": self._status.value,
            "sim_time_seconds": self._sim_time,
            "tick_count": self._tick_count,
            "entity_count": len(self._entities),
            "max_entities": self._max_entities,
        }

    def get_entity_distances(self) -> Dict[str, Dict[str, float]]:
        """Return full distance matrix for tactical proximity analysis."""
        matrix: Dict[str, Dict[str, float]] = {}
        for left_id, left in self._entities.items():
            matrix[left_id] = {}
            for right_id, right in self._entities.items():
                matrix[left_id][right_id] = 0.0 if left_id == right_id else left.distance_to(right)
        return matrix
