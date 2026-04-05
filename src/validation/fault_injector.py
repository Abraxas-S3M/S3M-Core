"""Fault injection primitives for tactical replay stress testing.

Military/tactical context:
These faults emulate degraded sensors, contested links, spoofing, stale tracks,
and compute saturation so crews can validate survivability logic under stress.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Mapping, Optional
from uuid import uuid4
import random
import time

from src.platforms.common import ThreatPriority, Track


class FaultType(str, Enum):
    """Supported tactical fault categories for closed-range validation."""

    SENSOR_DROPOUT = "sensor_dropout"
    LINK_LOSS = "link_loss"
    GPS_SPOOF = "gps_spoof"
    STALE_TRACKS = "stale_tracks"
    CPU_OVERLOAD = "cpu_overload"


class ScheduleMode(str, Enum):
    """Schedule strategy for triggering synthetic tactical faults."""

    RANDOM = "random"
    PERIODIC = "periodic"
    TRIGGERED = "triggered"


@dataclass(frozen=True)
class FaultScheduleEntry:
    """One scheduled fault activation policy."""

    entry_id: str
    fault_type: FaultType
    schedule_mode: ScheduleMode = ScheduleMode.PERIODIC
    start_time_s: float = 0.0
    duration_s: float = 2.0
    interval_s: float = 5.0
    probability: float = 0.25
    trigger_key: str | None = None
    target_platforms: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActiveFault:
    """Runtime tracking for active faults and optional restoration hooks."""

    activation_id: str
    entry_id: str
    fault_type: FaultType
    platform_id: str | None
    start_time_s: float
    end_time_s: float
    details: dict[str, Any] = field(default_factory=dict)
    restore_callback: Callable[[], None] | None = None


class FaultInjector:
    """Injects and schedules validation faults against adapters and state."""

    DEFAULT_SENSORS: tuple[str, ...] = ("radar", "eo", "ir", "gps", "ais")

    def __init__(
        self,
        schedule: list[FaultScheduleEntry] | None = None,
        *,
        random_seed: int = 7,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.schedule = list(schedule or [])
        self._rng = random.Random(random_seed)
        self._sleep_fn = sleep_fn
        self._active_faults: list[ActiveFault] = []
        self._last_activation_s: dict[str, float] = {}
        self._last_random_check_s: dict[str, float] = {}

    @property
    def active_faults(self) -> list[dict[str, Any]]:
        """Current active fault set for debug/audit surfaces."""
        return [
            {
                "activation_id": item.activation_id,
                "entry_id": item.entry_id,
                "fault_type": item.fault_type.value,
                "platform_id": item.platform_id,
                "start_time_s": item.start_time_s,
                "end_time_s": item.end_time_s,
                "details": dict(item.details),
            }
            for item in self._active_faults
        ]

    def run_scheduled_injections(
        self,
        *,
        sim_time_s: float,
        adapters: Mapping[str, Any],
        platform_states: Mapping[str, Any],
        track_store: Any | None = None,
        trigger_flags: Mapping[str, bool] | None = None,
    ) -> list[dict[str, Any]]:
        """Activate schedule entries at the current replay time."""

        self._expire_faults(sim_time_s)
        events: list[dict[str, Any]] = []
        for entry in self.schedule:
            if not self._should_activate(entry, sim_time_s, trigger_flags or {}):
                continue
            activations = self._activate_entry(
                entry=entry,
                sim_time_s=sim_time_s,
                adapters=adapters,
                platform_states=platform_states,
                track_store=track_store,
            )
            self._last_activation_s[entry.entry_id] = sim_time_s
            events.extend(activations)
        return events

    def apply_active_effects(self, *, platform_id: str, state: Any, sim_time_s: float) -> Any:
        """Apply active continuous faults to the current platform state."""

        self._expire_faults(sim_time_s)
        for active in self._active_faults:
            if active.platform_id not in (None, platform_id):
                continue
            if active.fault_type == FaultType.LINK_LOSS:
                setattr(state, "comms_status", "lost")
            elif active.fault_type == FaultType.GPS_SPOOF:
                spoofed = active.details.get("spoofed_position", state.position)
                setattr(state, "true_position", tuple(state.position))
                state.position = tuple(spoofed)
                setattr(state, "gps_spoofed", True)
        return state

    def _activate_entry(
        self,
        *,
        entry: FaultScheduleEntry,
        sim_time_s: float,
        adapters: Mapping[str, Any],
        platform_states: Mapping[str, Any],
        track_store: Any | None,
    ) -> list[dict[str, Any]]:
        targets = entry.target_platforms or [None]
        results: list[dict[str, Any]] = []
        for platform_id in targets:
            adapter = adapters.get(platform_id) if platform_id else None
            state = platform_states.get(platform_id) if platform_id else None
            active_fault: ActiveFault | None = None
            stale_track_ids: list[str] = []

            if entry.fault_type == FaultType.SENSOR_DROPOUT and adapter is not None:
                active_fault = self.inject_sensor_dropout(
                    adapter=adapter,
                    sim_time_s=sim_time_s,
                    duration_s=entry.duration_s,
                    sensors=entry.config.get("sensors"),
                    dropout_count=int(entry.config.get("dropout_count", 1)),
                    entry_id=entry.entry_id,
                    platform_id=platform_id,
                )
            elif entry.fault_type == FaultType.LINK_LOSS and state is not None:
                active_fault = self.inject_link_loss(
                    state=state,
                    sim_time_s=sim_time_s,
                    duration_s=entry.duration_s,
                    entry_id=entry.entry_id,
                    platform_id=platform_id,
                )
            elif entry.fault_type == FaultType.GPS_SPOOF and state is not None:
                spoofed = tuple(entry.config.get("false_coordinates", state.position))
                active_fault = self.inject_gps_spoof(
                    state=state,
                    false_coordinates=spoofed,
                    sim_time_s=sim_time_s,
                    duration_s=entry.duration_s,
                    entry_id=entry.entry_id,
                    platform_id=platform_id,
                )
            elif entry.fault_type == FaultType.STALE_TRACKS and track_store is not None:
                stale_track_ids = self.inject_stale_tracks(
                    track_store=track_store,
                    sim_time_s=sim_time_s,
                    stale_count=int(entry.config.get("stale_count", 1)),
                    staleness_s=float(entry.config.get("staleness_s", max(30.0, entry.duration_s * 3.0))),
                    classification=str(entry.config.get("classification", "unknown")),
                )
            elif entry.fault_type == FaultType.CPU_OVERLOAD and adapter is not None:
                active_fault = self.inject_cpu_overload(
                    adapter=adapter,
                    sim_time_s=sim_time_s,
                    duration_s=entry.duration_s,
                    delay_s=float(entry.config.get("delay_s", 0.01)),
                    method_names=list(entry.config.get("method_names", [])),
                    entry_id=entry.entry_id,
                    platform_id=platform_id,
                )

            if active_fault is not None:
                self._active_faults.append(active_fault)
                results.append(
                    {
                        "entry_id": entry.entry_id,
                        "fault_type": entry.fault_type.value,
                        "platform_id": platform_id,
                        "sim_time_s": sim_time_s,
                        "duration_s": entry.duration_s,
                        "details": dict(active_fault.details),
                    }
                )
            elif stale_track_ids:
                results.append(
                    {
                        "entry_id": entry.entry_id,
                        "fault_type": entry.fault_type.value,
                        "platform_id": platform_id,
                        "sim_time_s": sim_time_s,
                        "duration_s": entry.duration_s,
                        "details": {"stale_track_ids": stale_track_ids},
                    }
                )
        return results

    def _should_activate(
        self,
        entry: FaultScheduleEntry,
        sim_time_s: float,
        trigger_flags: Mapping[str, bool],
    ) -> bool:
        if sim_time_s < entry.start_time_s:
            return False

        if entry.schedule_mode == ScheduleMode.PERIODIC:
            if entry.entry_id not in self._last_activation_s:
                return True
            interval = max(0.01, float(entry.interval_s))
            return (sim_time_s - self._last_activation_s[entry.entry_id]) >= interval

        if entry.schedule_mode == ScheduleMode.RANDOM:
            interval = max(0.01, float(entry.interval_s))
            last_check = self._last_random_check_s.get(entry.entry_id, float("-inf"))
            if (sim_time_s - last_check) < interval:
                return False
            self._last_random_check_s[entry.entry_id] = sim_time_s
            probability = max(0.0, min(1.0, float(entry.probability)))
            return self._rng.random() <= probability

        key = entry.trigger_key or entry.entry_id
        if not trigger_flags.get(key, False):
            return False
        cooldown = max(0.01, float(entry.interval_s or entry.duration_s))
        if entry.entry_id not in self._last_activation_s:
            return True
        return (sim_time_s - self._last_activation_s[entry.entry_id]) >= cooldown

    def _expire_faults(self, sim_time_s: float) -> None:
        retained: list[ActiveFault] = []
        for fault in self._active_faults:
            if sim_time_s < fault.end_time_s:
                retained.append(fault)
                continue
            if fault.restore_callback is not None:
                fault.restore_callback()
        self._active_faults = retained

    def inject_sensor_dropout(
        self,
        *,
        adapter: Any,
        sim_time_s: float,
        duration_s: float,
        sensors: list[str] | None,
        dropout_count: int,
        entry_id: str,
        platform_id: str | None,
    ) -> ActiveFault:
        """Disable random onboard sensors for the given duration."""

        available = list(sensors or getattr(adapter, "sensors", self.DEFAULT_SENSORS))
        if not available:
            available = list(self.DEFAULT_SENSORS)
        disable_count = max(1, min(len(available), int(dropout_count)))
        disabled = sorted(self._rng.sample(available, disable_count))
        previous_disabled = set(getattr(adapter, "disabled_sensors", set()))
        combined = set(previous_disabled)
        combined.update(disabled)
        setattr(adapter, "disabled_sensors", combined)

        def _restore() -> None:
            setattr(adapter, "disabled_sensors", previous_disabled)

        return ActiveFault(
            activation_id=f"fault-{uuid4().hex[:10]}",
            entry_id=entry_id,
            fault_type=FaultType.SENSOR_DROPOUT,
            platform_id=platform_id,
            start_time_s=sim_time_s,
            end_time_s=sim_time_s + max(0.01, duration_s),
            details={"disabled_sensors": disabled},
            restore_callback=_restore,
        )

    def inject_link_loss(
        self,
        *,
        state: Any,
        sim_time_s: float,
        duration_s: float,
        entry_id: str,
        platform_id: str | None,
    ) -> ActiveFault:
        """Force communications status to lost for a tactical outage window."""

        prior_status = getattr(state, "comms_status", "ok")
        setattr(state, "comms_status", "lost")
        return ActiveFault(
            activation_id=f"fault-{uuid4().hex[:10]}",
            entry_id=entry_id,
            fault_type=FaultType.LINK_LOSS,
            platform_id=platform_id,
            start_time_s=sim_time_s,
            end_time_s=sim_time_s + max(0.01, duration_s),
            details={"prior_comms_status": prior_status},
        )

    def inject_gps_spoof(
        self,
        *,
        state: Any,
        false_coordinates: tuple[float, float, float],
        sim_time_s: float,
        duration_s: float,
        entry_id: str,
        platform_id: str | None,
    ) -> ActiveFault:
        """Inject false geolocation into the tactical state stream."""

        original_position = tuple(state.position)
        state.position = tuple(false_coordinates)
        setattr(state, "gps_spoofed", True)
        setattr(state, "true_position", original_position)
        return ActiveFault(
            activation_id=f"fault-{uuid4().hex[:10]}",
            entry_id=entry_id,
            fault_type=FaultType.GPS_SPOOF,
            platform_id=platform_id,
            start_time_s=sim_time_s,
            end_time_s=sim_time_s + max(0.01, duration_s),
            details={
                "spoofed_position": tuple(false_coordinates),
                "true_position": original_position,
            },
        )

    def inject_stale_tracks(
        self,
        *,
        track_store: Any,
        sim_time_s: float,
        stale_count: int,
        staleness_s: float,
        classification: str,
    ) -> list[str]:
        """Inject outdated tracks into TrackStore to test stale-data rejection."""

        injected_ids: list[str] = []
        stale_age = max(1.0, float(staleness_s))
        now = datetime.now(timezone.utc) - timedelta(seconds=sim_time_s)
        for _ in range(max(1, stale_count)):
            track_id = f"stale-{uuid4().hex[:8]}"
            position = (
                self._rng.uniform(100.0, 600.0),
                self._rng.uniform(-200.0, 200.0),
                self._rng.uniform(0.0, 50.0),
            )
            stale_track = Track(
                track_id=track_id,
                position=position,
                confidence=0.35,
                classification=classification,
                threat_priority=ThreatPriority.LOW,
                last_seen=now - timedelta(seconds=stale_age),
            )
            track_store.ingest_track(stale_track)
            injected_ids.append(track_id)
        return injected_ids

    def inject_cpu_overload(
        self,
        *,
        adapter: Any,
        sim_time_s: float,
        duration_s: float,
        delay_s: float,
        method_names: list[str],
        entry_id: str,
        platform_id: str | None,
    ) -> ActiveFault:
        """Add artificial delay wrappers to adapter methods."""

        methods = method_names or ["read_state", "inject_simulated_telemetry", "connect"]
        original: dict[str, Callable[..., Any]] = {}
        for name in methods:
            method = getattr(adapter, name, None)
            if not callable(method):
                continue
            original[name] = method

            def _wrapper(*args: Any, __method: Callable[..., Any] = method, **kwargs: Any) -> Any:
                self._sleep_fn(max(0.0, delay_s))
                return __method(*args, **kwargs)

            setattr(adapter, name, _wrapper)

        def _restore() -> None:
            for name, method in original.items():
                setattr(adapter, name, method)

        return ActiveFault(
            activation_id=f"fault-{uuid4().hex[:10]}",
            entry_id=entry_id,
            fault_type=FaultType.CPU_OVERLOAD,
            platform_id=platform_id,
            start_time_s=sim_time_s,
            end_time_s=sim_time_s + max(0.01, duration_s),
            details={
                "delay_s": max(0.0, float(delay_s)),
                "delayed_methods": sorted(original.keys()),
            },
            restore_callback=_restore,
        )
