"""Panopticon REST adapter for Layer 04 simulator interoperability."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import logging

from src.simulation.adapters.base_adapter import GenericSimAdapter
from src.simulation.models import EntityType, ScenarioDefinition, SimConfig, SimEntity, SimulationState, SimulatorStatus

LOGGER = logging.getLogger(__name__)


class PanopticonAdapter(GenericSimAdapter):
    """HTTP-only adapter preserving offline portability with stdlib urllib."""

    def __init__(self, config: SimConfig) -> None:
        config.host = config.host or "localhost"
        if config.port == 0:
            config.port = 5000
        super().__init__(config)
        self._status = SimulatorStatus.DISCONNECTED
        self._connected = False
        self._available = False
        self._sim_time = 0.0
        self._tick_count = 0
        self._last_state = self._empty_state()

    def _base_url(self) -> str:
        return f"http://{self.config.host}:{self.config.port}"

    def _empty_state(self) -> SimulationState:
        return SimulationState(
            timestamp=datetime.now(timezone.utc),
            sim_time_seconds=self._sim_time,
            entities=[],
            terrain={},
            weather={},
            active_events=[],
            metadata={"simulator": "panopticon", "tick_count": self._tick_count},
        )

    def _http_json(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        body = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        req = Request(url=f"{self._base_url()}{path}", data=body, method=method, headers=headers)
        try:
            with urlopen(req, timeout=2.0) as response:
                text = response.read().decode("utf-8")
                return json.loads(text) if text.strip() else {}
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return None

    def connect(self) -> bool:
        self._status = SimulatorStatus.CONNECTING
        data = self._http_json("GET", "/api/health")
        if data is None:
            LOGGER.warning("Panopticon server not running — adapter unavailable")
            self._available = False
            self._connected = False
            self._status = SimulatorStatus.ERROR
            return False
        self._available = True
        self._connected = True
        self._status = SimulatorStatus.CONNECTED
        return True

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

    def _state_from_payload(self, payload: Dict[str, Any]) -> SimulationState:
        entities: list[SimEntity] = []
        for raw in payload.get("entities", []):
            if not isinstance(raw, dict):
                continue
            try:
                entities.append(
                    SimEntity(
                        entity_id=str(raw.get("entity_id", "unknown")),
                        entity_type=EntityType(str(raw.get("entity_type", EntityType.UNKNOWN.value))),
                        position=tuple(raw.get("position", (0.0, 0.0, 0.0))),
                        velocity=tuple(raw.get("velocity", (0.0, 0.0, 0.0))),
                        heading=float(raw.get("heading", 0.0)),
                        health=float(raw.get("health", 1.0)),
                        active=bool(raw.get("active", True)),
                        metadata=dict(raw.get("metadata", {})),
                    )
                )
            except Exception:
                continue

        return SimulationState(
            timestamp=datetime.now(timezone.utc),
            sim_time_seconds=float(payload.get("sim_time_seconds", self._sim_time)),
            entities=entities,
            terrain=dict(payload.get("terrain", {})),
            weather=dict(payload.get("weather", {})),
            active_events=list(payload.get("active_events", [])),
            metadata=dict(payload.get("metadata", {"simulator": "panopticon", "tick_count": self._tick_count})),
        )

    def step(self, dt: float = 0.1) -> SimulationState:
        if not self.is_connected():
            return self._last_state
        data = self._http_json("POST", "/api/step", {"dt": float(dt)})
        if data is None:
            return self._last_state
        self._sim_time = float(data.get("sim_time_seconds", self._sim_time + float(dt)))
        self._tick_count += 1
        self._status = SimulatorStatus.RUNNING
        self._last_state = self._state_from_payload(data)
        return self._last_state

    def get_state(self) -> SimulationState:
        if not self.is_connected():
            return self._last_state
        data = self._http_json("GET", "/api/state")
        if data is not None:
            self._last_state = self._state_from_payload(data)
        return self._last_state

    def spawn_entity(
        self,
        entity_type: EntityType,
        position: Tuple[float, float, float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not self.is_connected():
            return ""
        data = self._http_json(
            "POST",
            "/api/entities",
            {
                "entity_type": entity_type.value if isinstance(entity_type, EntityType) else str(entity_type),
                "position": list(position),
                "metadata": metadata or {},
            },
        )
        if data is None:
            return ""
        return str(data.get("entity_id", ""))

    def remove_entity(self, entity_id: str) -> None:
        if not self.is_connected() or not entity_id:
            return
        self._http_json("POST", f"/api/entities/{entity_id}/delete")

    def set_entity_target(self, entity_id: str, target_position: tuple, speed: float = 10.0) -> None:
        if not self.is_connected() or not entity_id:
            return
        self._http_json(
            "POST",
            f"/api/entities/{entity_id}/target",
            {"target_position": list(target_position), "speed": float(speed)},
        )

    def load_scenario(self, scenario: ScenarioDefinition) -> bool:
        if not self.is_connected():
            return False
        data = self._http_json("POST", "/api/scenarios/load", scenario.to_dict())
        return data is not None

    def get_sim_time(self) -> float:
        return self._sim_time

    def get_gymnasium_env(self) -> Optional[object]:
        """Return optional Gymnasium wrapper descriptor if server exposes it."""
        if not self.is_connected():
            return None
        return self._http_json("GET", "/api/gymnasium/env")

    def health_check(self) -> dict:
        return {
            "adapter": "panopticon",
            "available": self._available,
            "connected": self._connected,
            "status": self._status.value,
        }
