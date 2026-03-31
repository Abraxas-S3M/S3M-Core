"""JSBSim adapter with graceful offline fallback for non-installed environments."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
import logging

from src.simulation.adapters.base_adapter import GenericSimAdapter
from src.simulation.models import EntityType, ScenarioDefinition, SimConfig, SimEntity, SimulationState, SimulatorStatus

LOGGER = logging.getLogger(__name__)


class JSBSimAdapter(GenericSimAdapter):
    """Adapter for JSBSim flight dynamics integration."""

    def __init__(self, config: SimConfig) -> None:
        config.extra_params.setdefault("aircraft_model", "f16")
        config.extra_params.setdefault("dt", 0.00833)
        super().__init__(config)
        self._status = SimulatorStatus.DISCONNECTED
        self._available = False
        self._connected = False
        self._jsbsim = None
        self._fdmexecs: Dict[str, Any] = {}
        self._sim_time = 0.0
        self._tick_count = 0
        self._primary_id: Optional[str] = None
        self._last_state = self._empty_state()

    def _empty_state(self) -> SimulationState:
        return SimulationState(
            timestamp=datetime.now(timezone.utc),
            sim_time_seconds=self._sim_time,
            entities=[],
            terrain={},
            weather={},
            active_events=[],
            metadata={"simulator": "jsbsim", "tick_count": self._tick_count},
        )

    def _native_dt(self) -> float:
        return float(self.config.extra_params.get("dt", 0.00833))

    def _create_fdm(self, entity_id: str) -> bool:
        if not self._available or self._jsbsim is None:
            return False
        try:
            fdm = self._jsbsim.FGFDMExec(None)
            model = str(self.config.extra_params.get("aircraft_model", "f16"))
            fdm.load_model(model)
            fdm.set_dt(self._native_dt())
            fdm.set_property_value("ic/h-sl-ft", 5000.0)
            fdm.set_property_value("ic/u-fps", 300.0)
            fdm.set_property_value("ic/psi-true-deg", 0.0)
            fdm.run_ic()
            self._fdmexecs[entity_id] = fdm
            self._primary_id = self._primary_id or entity_id
            return True
        except Exception as exc:
            LOGGER.error("JSBSim FDM creation failed: %s", exc)
            return False

    def connect(self) -> bool:
        try:
            import jsbsim  # type: ignore

            self._jsbsim = jsbsim
            self._available = True
            self._connected = self._create_fdm("jsbsim-primary")
            self._status = SimulatorStatus.CONNECTED if self._connected else SimulatorStatus.ERROR
            return self._connected
        except ImportError:
            LOGGER.warning("jsbsim package not installed — JSBSim adapter unavailable")
            self._available = False
            self._connected = False
            self._status = SimulatorStatus.ERROR
            return False
        except Exception as exc:
            LOGGER.error("JSBSim connect failed: %s", exc)
            self._available = False
            self._connected = False
            self._status = SimulatorStatus.ERROR
            return False

    def disconnect(self) -> None:
        self._fdmexecs.clear()
        self._primary_id = None
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

    def _entity_from_fdm(self, entity_id: str, fdm: Any) -> SimEntity:
        lat = float(fdm.get_property_value("position/lat-gc-deg"))
        lon = float(fdm.get_property_value("position/long-gc-deg"))
        alt_ft = float(fdm.get_property_value("position/h-sl-ft"))
        x = lon * 111_320.0
        y = lat * 110_540.0
        z = alt_ft * 0.3048
        vx = float(fdm.get_property_value("velocities/u-fps")) * 0.3048
        vy = float(fdm.get_property_value("velocities/v-fps")) * 0.3048
        vz = float(fdm.get_property_value("velocities/w-fps")) * 0.3048
        heading = float(fdm.get_property_value("attitude/psi-deg"))
        return SimEntity(
            entity_id=entity_id,
            entity_type=EntityType.FRIENDLY_UAV,
            position=(x, y, z),
            velocity=(vx, vy, vz),
            heading=heading,
            health=1.0,
            active=True,
            metadata={"source": "jsbsim"},
        )

    def step(self, dt: float = 0.1) -> SimulationState:
        if not self.is_connected():
            return self._last_state
        dt = max(0.0, float(dt))
        substeps = max(1, int(round(dt / max(self._native_dt(), 1e-6))))
        try:
            for _ in range(substeps):
                for fdm in self._fdmexecs.values():
                    fdm.run()
        except Exception:
            self._status = SimulatorStatus.ERROR
            return self._last_state

        entities = [self._entity_from_fdm(entity_id, fdm) for entity_id, fdm in self._fdmexecs.items()]
        self._sim_time += dt
        self._tick_count += 1
        self._status = SimulatorStatus.RUNNING
        self._last_state = SimulationState(
            timestamp=datetime.now(timezone.utc),
            sim_time_seconds=self._sim_time,
            entities=entities,
            terrain={},
            weather={},
            active_events=[],
            metadata={"simulator": "jsbsim", "tick_count": self._tick_count},
        )
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
        if len(self._fdmexecs) >= 4:
            return ""
        entity_id = f"jsbsim-{len(self._fdmexecs) + 1}"
        return entity_id if self._create_fdm(entity_id) else ""

    def remove_entity(self, entity_id: str) -> None:
        self._fdmexecs.pop(entity_id, None)
        if self._primary_id == entity_id:
            self._primary_id = next(iter(self._fdmexecs.keys()), None)

    def set_entity_target(self, entity_id: str, target_position: tuple, speed: float = 10.0) -> None:
        fdm = self._fdmexecs.get(entity_id)
        if fdm is None:
            return
        try:
            fdm.set_property_value("ap/heading_setpoint", float(target_position[0]) % 360.0)
            fdm.set_property_value("ap/altitude_setpoint", max(500.0, float(target_position[2]) / 0.3048))
            fdm.set_property_value("ap/airspeed_setpoint", max(50.0, float(speed) / 0.3048))
        except Exception:
            return

    def load_scenario(self, scenario: ScenarioDefinition) -> bool:
        return self.is_connected()

    def get_sim_time(self) -> float:
        return self._sim_time

    def get_flight_data(self) -> dict:
        """Return key telemetry values for aircraft mission monitoring."""
        if self._primary_id is None:
            return {}
        fdm = self._fdmexecs.get(self._primary_id)
        if fdm is None:
            return {}
        try:
            return {
                "airspeed": float(fdm.get_property_value("velocities/vtrue-fps")) * 0.3048,
                "altitude": float(fdm.get_property_value("position/h-sl-ft")) * 0.3048,
                "g_load": float(fdm.get_property_value("accelerations/n-pilot-z-norm")),
                "fuel": float(fdm.get_property_value("propulsion/total-fuel-lbs")),
                "engine_rpm": float(fdm.get_property_value("propulsion/engine[0]/rpm")),
            }
        except Exception:
            return {}

    def set_controls(self, aileron, elevator, rudder, throttle) -> None:
        if self._primary_id is None:
            return
        fdm = self._fdmexecs.get(self._primary_id)
        if fdm is None:
            return
        try:
            fdm.set_property_value("fcs/aileron-cmd-norm", float(aileron))
            fdm.set_property_value("fcs/elevator-cmd-norm", float(elevator))
            fdm.set_property_value("fcs/rudder-cmd-norm", float(rudder))
            fdm.set_property_value("fcs/throttle-cmd-norm", float(throttle))
        except Exception:
            return

    def health_check(self) -> dict:
        return {
            "adapter": "jsbsim",
            "available": self._available,
            "connected": self._connected,
            "status": self._status.value,
            "aircraft_count": len(self._fdmexecs),
        }
