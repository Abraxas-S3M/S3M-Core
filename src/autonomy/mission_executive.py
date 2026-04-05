"""Mission executive layer above behavior trees for tactical phase control.

The mission executive manages high-level mission phase transitions and emits
only mobility/sensor commands. Payload control is intentionally excluded so
weapons release always remains in the engagement authorization pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import inspect
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple
import uuid

try:
    from src.platforms.common.messages import MobilityCommand, SensorCommand  # type: ignore
except Exception:  # pragma: no cover - fallback for repos that do not have Prompt 1 yet.
    @dataclass
    class MobilityCommand:
        """Fallback mobility message for standalone autonomy tests."""

        command: str
        parameters: Dict[str, Any] = field(default_factory=dict)
        mission_id: Optional[str] = None

    @dataclass
    class SensorCommand:
        """Fallback sensor message for standalone autonomy tests."""

        command: str
        parameters: Dict[str, Any] = field(default_factory=dict)
        mission_id: Optional[str] = None


class MissionPhase(str, Enum):
    """Mission lifecycle phases controlled by the executive."""

    IDLE = "idle"
    DEPLOY = "deploy"
    TRANSIT = "transit"
    ON_STATION = "on_station"
    EGRESS = "egress"
    RTB = "rtb"
    PAUSED = "paused"
    ABORTED = "aborted"
    COMPLETE = "complete"


class ExecutiveMissionType(str, Enum):
    """Mission types supported by the executive tick handlers."""

    PATROL = "patrol"
    CONVOY = "convoy"
    ESCORT = "escort"
    PERIMETER_SCAN = "perimeter_scan"
    RTB = "rtb"
    STATION_KEEP = "station_keep"
    LOITER = "loiter"
    INTERCEPT = "intercept"
    ISR = "isr"


class MissionExecutive:
    """Top-level mission phase controller above lower-level behavior trees."""

    def __init__(
        self,
        behavior_executor: Any | None = None,
        fuel_critical_pct: float = 15.0,
    ) -> None:
        self.behavior_executor = behavior_executor
        self.fuel_critical_pct = max(1.0, min(50.0, float(fuel_critical_pct)))
        self.phase: MissionPhase = MissionPhase.IDLE
        self.mission_type: Optional[ExecutiveMissionType] = None
        self.mission_id: Optional[str] = None
        self.context: Dict[str, Any] = {}
        self.transition_log: List[Dict[str, Any]] = []
        self._paused_from: MissionPhase = MissionPhase.IDLE
        self._aborted: bool = False
        self._patrol_idx: int = 0
        self._perimeter_idx: int = 0
        self._started_at: Optional[datetime] = None

    def start_mission(
        self,
        mission_type: ExecutiveMissionType | str,
        mission_context: Optional[Mapping[str, Any]] = None,
        mission_id: Optional[str] = None,
    ) -> None:
        """Initialize mission state and move from idle to deploy."""
        self.mission_type = ExecutiveMissionType(mission_type)
        self.mission_id = mission_id or f"exec-{uuid.uuid4().hex[:10]}"
        self.context = dict(mission_context or {})
        self._patrol_idx = 0
        self._perimeter_idx = 0
        self._aborted = False
        self._started_at = datetime.now(timezone.utc)
        self._transition(MissionPhase.DEPLOY, "mission_started")
        if self.behavior_executor is not None and hasattr(self.behavior_executor, "start"):
            # Tactical context: behavior trees remain subordinate to mission-phase
            # authority and are initialized with the same mission context.
            self.behavior_executor.start(self.context)

    def update(self, telemetry: Optional[Mapping[str, Any]] = None) -> List[Any]:
        """Advance one mission tick and emit mobility/sensor commands."""
        if telemetry:
            self.context.update(dict(telemetry))
        if self.phase in {MissionPhase.IDLE, MissionPhase.COMPLETE, MissionPhase.ABORTED, MissionPhase.PAUSED}:
            return []

        self._apply_safety_overrides()

        if self.phase == MissionPhase.DEPLOY:
            return self._tick_deploy()
        if self.phase == MissionPhase.TRANSIT:
            return self._tick_transit()
        if self.phase == MissionPhase.ON_STATION:
            if bool(self.context.get("mission_complete", False)) and self.mission_type != ExecutiveMissionType.RTB:
                self._transition(MissionPhase.EGRESS, "mission_complete_flag")
                return self._tick_egress()
            return self._tick_on_station()
        if self.phase == MissionPhase.EGRESS:
            return self._tick_egress()
        if self.phase == MissionPhase.RTB:
            return self._tick_rtb()
        return []

    def pause(self) -> None:
        """Pause mission progression without discarding mission state."""
        if self.phase in {MissionPhase.IDLE, MissionPhase.COMPLETE, MissionPhase.ABORTED, MissionPhase.PAUSED}:
            return
        self._paused_from = self.phase
        self.phase = MissionPhase.PAUSED
        if self.behavior_executor is not None and hasattr(self.behavior_executor, "pause"):
            self.behavior_executor.pause()

    def resume(self) -> None:
        """Resume mission from paused phase."""
        if self.phase != MissionPhase.PAUSED:
            return
        self.phase = self._paused_from
        if self.behavior_executor is not None and hasattr(self.behavior_executor, "resume"):
            self.behavior_executor.resume()

    def abort(self) -> None:
        """Abort mission and stop subordinate execution layers."""
        self._aborted = True
        self.phase = MissionPhase.ABORTED
        if self.behavior_executor is not None and hasattr(self.behavior_executor, "abort"):
            self.behavior_executor.abort()
        self.transition_log.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from": str(self._paused_from.value),
                "to": MissionPhase.ABORTED.value,
                "reason": "abort",
            }
        )

    def _tick_deploy(self) -> List[Any]:
        commands: List[Any] = [
            self._emit_sensor("sensor_self_test", profile="startup"),
            self._emit_mobility("launch_sequence", mode="autonomy"),
        ]
        self._transition(MissionPhase.TRANSIT, "deploy_complete")
        return commands

    def _tick_transit(self) -> List[Any]:
        target = self._station_target()
        if target and self._at_position(target, tolerance_m=float(self.context.get("on_station_tolerance_m", 25.0))):
            self._transition(MissionPhase.ON_STATION, "arrived_on_station")
            return [
                self._emit_mobility("hold_position", target=target),
                self._emit_sensor("sector_scan", profile="on_station_entry"),
            ]
        return [
            self._emit_mobility("navigate_to", target=target or [0.0, 0.0, 0.0], speed_mps=self.context.get("transit_speed_mps", 20.0)),
            self._emit_sensor("route_scan", profile="transit"),
        ]

    def _tick_on_station(self) -> List[Any]:
        if self.mission_type is None:
            return []
        if self.behavior_executor is not None and hasattr(self.behavior_executor, "tick"):
            try:
                self.context["behavior_tree_status"] = str(self.behavior_executor.tick())
            except Exception:
                self.context["behavior_tree_status"] = "tick_error"

        if self.mission_type == ExecutiveMissionType.PATROL:
            return self._tick_patrol()
        if self.mission_type == ExecutiveMissionType.CONVOY:
            return self._tick_convoy()
        if self.mission_type == ExecutiveMissionType.ESCORT:
            return self._tick_escort()
        if self.mission_type == ExecutiveMissionType.PERIMETER_SCAN:
            return self._tick_perimeter()
        if self.mission_type == ExecutiveMissionType.RTB:
            self._transition(MissionPhase.RTB, "rtb_mission_type")
            return self._tick_rtb()
        if self.mission_type == ExecutiveMissionType.STATION_KEEP:
            return self._tick_station_keep()
        if self.mission_type == ExecutiveMissionType.LOITER:
            return self._tick_loiter()
        if self.mission_type == ExecutiveMissionType.INTERCEPT:
            return self._tick_intercept()
        return self._tick_isr()

    def _tick_egress(self) -> List[Any]:
        self._transition(MissionPhase.RTB, "egress_to_rtb")
        return [self._emit_mobility("egress_route", target=self.context.get("base_position", [0.0, 0.0, 0.0]))]

    def _tick_patrol(self) -> List[Any]:
        waypoints = self._as_waypoint_list(self.context.get("waypoints", []))
        if not waypoints:
            return [self._emit_mobility("hold_position"), self._emit_sensor("sector_scan", profile="patrol_no_waypoints")]
        waypoint = waypoints[self._patrol_idx]
        if self._at_position(waypoint, tolerance_m=float(self.context.get("waypoint_tolerance_m", 15.0))):
            if self._patrol_idx < len(waypoints) - 1:
                self._patrol_idx += 1
            elif bool(self.context.get("patrol_loop", True)):
                self._patrol_idx = 0
            else:
                self.context["mission_complete"] = True
        return [
            self._emit_mobility("waypoint_follow", waypoint=waypoint, index=self._patrol_idx),
            self._emit_sensor("wide_area_scan", profile="patrol"),
        ]

    def _tick_convoy(self) -> List[Any]:
        lead_position = self._coerce_xyz(self.context.get("convoy_lead_position", (0.0, 0.0, 0.0)))
        standoff_m = float(self.context.get("convoy_standoff_m", 60.0))
        return [
            self._emit_mobility("follow_convoy", lead_position=lead_position, standoff_m=standoff_m),
            self._emit_sensor("flank_watch", profile="convoy_protection"),
        ]

    def _tick_escort(self) -> List[Any]:
        asset_position = self._coerce_xyz(self.context.get("protected_asset_position", (0.0, 0.0, 0.0)))
        radius_m = float(self.context.get("escort_radius_m", 120.0))
        return [
            self._emit_mobility("escort_orbit", center=asset_position, radius_m=radius_m),
            self._emit_sensor("threat_search", profile="escort"),
        ]

    def _tick_perimeter(self) -> List[Any]:
        perimeter = self._as_waypoint_list(self.context.get("perimeter_points", []))
        if not perimeter:
            center = self._station_target() or [0.0, 0.0, 0.0]
            perimeter = [center]
        target = perimeter[self._perimeter_idx]
        if self._at_position(target, tolerance_m=float(self.context.get("perimeter_tolerance_m", 20.0))):
            self._perimeter_idx = (self._perimeter_idx + 1) % len(perimeter)
        return [
            self._emit_mobility("perimeter_leg", target=target, leg_index=self._perimeter_idx),
            self._emit_sensor("sector_scan", profile="perimeter", sector_index=self._perimeter_idx),
        ]

    def _tick_rtb(self) -> List[Any]:
        base = self._coerce_xyz(self.context.get("base_position", (0.0, 0.0, 0.0)))
        if self._at_position(base, tolerance_m=float(self.context.get("base_tolerance_m", 20.0))):
            self._transition(MissionPhase.COMPLETE, "arrived_base")
            return [
                self._emit_mobility("disarm_and_hold", target=base),
                self._emit_sensor("sensor_safe_mode", profile="rtb_complete"),
            ]
        return [
            self._emit_mobility("return_to_base", target=base, reason=self.context.get("rtb_reason", "mission_plan")),
            self._emit_sensor("defensive_scan", profile="rtb"),
        ]

    def _tick_station_keep(self) -> List[Any]:
        station = self._station_target() or [0.0, 0.0, 0.0]
        return [
            self._emit_mobility("station_keep", target=station),
            self._emit_sensor("persistent_watch", profile="station_keep"),
        ]

    def _tick_loiter(self) -> List[Any]:
        center = self._station_target() or [0.0, 0.0, 0.0]
        radius_m = float(self.context.get("loiter_radius_m", 250.0))
        return [
            self._emit_mobility("loiter_orbit", center=center, radius_m=radius_m),
            self._emit_sensor("intermittent_scan", profile="loiter"),
        ]

    def _tick_intercept(self) -> List[Any]:
        target = self._coerce_xyz(self.context.get("intercept_target_position", self._station_target() or (0.0, 0.0, 0.0)))
        if self._at_position(target, tolerance_m=float(self.context.get("intercept_tolerance_m", 40.0))):
            self.context["mission_complete"] = True
        return [
            self._emit_mobility("intercept_course", target=target, speed_mps=self.context.get("intercept_speed_mps", 45.0)),
            self._emit_sensor("target_lock_scan", profile="intercept"),
        ]

    def _tick_isr(self) -> List[Any]:
        station = self._station_target() or [0.0, 0.0, 0.0]
        return [
            self._emit_mobility("isr_racetrack", anchor=station, leg_m=self.context.get("isr_leg_m", 1200.0)),
            self._emit_sensor("high_res_collect", profile="isr"),
        ]

    def _apply_safety_overrides(self) -> None:
        if self.phase in {MissionPhase.RTB, MissionPhase.COMPLETE, MissionPhase.ABORTED}:
            return
        comms_status = str(self.context.get("comms_status", "nominal")).lower()
        fuel_pct = float(self.context.get("fuel_pct", 100.0))
        critical_fault = bool(self.context.get("critical_fault", False))
        critical_faults = self.context.get("critical_faults", [])
        if comms_status == "lost":
            self.context["rtb_reason"] = "comms_lost"
            self._transition(MissionPhase.RTB, "safety_comms_loss")
            return
        if fuel_pct <= self.fuel_critical_pct:
            self.context["rtb_reason"] = "fuel_critical"
            self._transition(MissionPhase.RTB, "safety_fuel_critical")
            return
        if critical_fault or (isinstance(critical_faults, Sequence) and len(critical_faults) > 0):
            self.context["rtb_reason"] = "critical_fault"
            self._transition(MissionPhase.RTB, "safety_critical_fault")

    def _transition(self, target_phase: MissionPhase, reason: str) -> None:
        if self.phase == target_phase:
            return
        self.transition_log.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from": self.phase.value,
                "to": target_phase.value,
                "reason": str(reason),
            }
        )
        self.phase = target_phase

    def _station_target(self) -> Optional[List[float]]:
        station = self.context.get("station_position")
        if station is not None:
            return [float(v) for v in self._coerce_xyz(station)]
        waypoints = self._as_waypoint_list(self.context.get("waypoints", []))
        if waypoints:
            return list(waypoints[0])
        return None

    def _at_position(self, target: Sequence[float], tolerance_m: float) -> bool:
        current = self._coerce_xyz(self.context.get("current_position", (0.0, 0.0, 0.0)))
        tgt = self._coerce_xyz(target)
        dx = current[0] - tgt[0]
        dy = current[1] - tgt[1]
        dz = current[2] - tgt[2]
        return (dx * dx + dy * dy + dz * dz) ** 0.5 <= max(0.1, float(tolerance_m))

    @staticmethod
    def _coerce_xyz(value: Any) -> Tuple[float, float, float]:
        if isinstance(value, (list, tuple)) and len(value) == 3:
            return (float(value[0]), float(value[1]), float(value[2]))
        return (0.0, 0.0, 0.0)

    def _as_waypoint_list(self, waypoints: Any) -> List[List[float]]:
        out: List[List[float]] = []
        if not isinstance(waypoints, Sequence):
            return out
        for wp in waypoints:
            if isinstance(wp, (list, tuple)) and len(wp) == 3:
                out.append([float(wp[0]), float(wp[1]), float(wp[2])])
        return out

    def _emit_mobility(self, command: str, **params: Any) -> Any:
        return _instantiate_message(MobilityCommand, command=command, params=params, mission_id=self.mission_id)

    def _emit_sensor(self, command: str, **params: Any) -> Any:
        return _instantiate_message(SensorCommand, command=command, params=params, mission_id=self.mission_id)


def _instantiate_message(message_cls: Any, command: str, params: Mapping[str, Any], mission_id: Optional[str]) -> Any:
    """Best-effort message creation compatible with multiple message schemas."""
    kwargs: Dict[str, Any] = {}
    now = datetime.now(timezone.utc).isoformat()

    signature = None
    try:
        signature = inspect.signature(message_cls)
    except Exception:
        signature = None

    param_names = set(signature.parameters.keys()) if signature is not None else set()
    if "command" in param_names:
        kwargs["command"] = command
    if "command_type" in param_names:
        kwargs["command_type"] = command
    if "action" in param_names:
        kwargs["action"] = command
    if "parameters" in param_names:
        kwargs["parameters"] = dict(params)
    if "params" in param_names:
        kwargs["params"] = dict(params)
    if "payload" in param_names:
        kwargs["payload"] = dict(params)
    if "mission_id" in param_names:
        kwargs["mission_id"] = mission_id
    if "timestamp" in param_names:
        kwargs["timestamp"] = now

    try:
        if kwargs:
            return message_cls(**kwargs)
        return message_cls(command=command, parameters=dict(params), mission_id=mission_id)
    except Exception:
        try:
            return message_cls(command, dict(params), mission_id)
        except Exception:
            return {
                "message_type": getattr(message_cls, "__name__", "UnknownMessage"),
                "command": command,
                "parameters": dict(params),
                "mission_id": mission_id,
                "timestamp": now,
            }


__all__ = [
    "MissionPhase",
    "ExecutiveMissionType",
    "MissionExecutive",
    "MobilityCommand",
    "SensorCommand",
]
