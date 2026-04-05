"""Telemetry replay harness for closed-range platform validation.

Military/tactical context:
This harness replays deterministic platform-state timelines into adapters so
teams can rehearse engagement and command-and-control logic offline before
fielding updates on range.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MethodType
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional
import copy
import json
import time

from src.platforms.common import AutonomyMode, HealthState, PlatformState, PlatformType


SUPPORTED_TIME_SCALES: tuple[int, ...] = (1, 2, 5, 10)


@dataclass
class ReplayFrame:
    """One timestamped platform state used for synchronized tactical replay."""

    platform_id: str
    sim_time_s: float
    state: PlatformState
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReplaySummary:
    """Execution summary for one replay pass."""

    platform_ids: list[str]
    frame_count: int
    injected_count: int
    wall_duration_s: float
    sim_duration_s: float
    time_scale: int
    synchronized: bool
    fault_events: list[dict[str, Any]] = field(default_factory=list)
    injection_log: list[dict[str, Any]] = field(default_factory=list)


class TelemetryReplayHarness:
    """Replay platform telemetry streams into adapters with time scaling."""

    def __init__(
        self,
        adapters: Mapping[str, Any],
        *,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if not adapters:
            raise ValueError("adapters must not be empty")
        self.adapters: dict[str, Any] = dict(adapters)
        self._frames_by_platform: dict[str, list[ReplayFrame]] = {}
        self._sleep_fn = sleep_fn
        self._injection_log: list[dict[str, Any]] = []
        self._install_injection_shims()

    def load_platform_state_sequence(
        self,
        json_path: str | Path,
        *,
        platform_id: str | None = None,
    ) -> list[ReplayFrame]:
        """Load one platform replay timeline from JSON.

        Accepted payload formats:
          1) {"platform_id": "...", "states": [...]}
          2) [{"sim_time_s": ..., "platform_id": "...", ...}, ...]
        """

        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"telemetry file not found: {path}")

        payload = json.loads(path.read_text(encoding="utf-8"))
        file_platform_id = platform_id
        raw_states: list[dict[str, Any]]
        if isinstance(payload, dict):
            if file_platform_id is None:
                file_platform_id = str(payload.get("platform_id", "")).strip() or None
            raw_states = list(payload.get("states", []))
        elif isinstance(payload, list):
            raw_states = list(payload)
        else:
            raise ValueError("telemetry payload must be a dict or list")

        if file_platform_id is None and raw_states:
            guessed = str(raw_states[0].get("platform_id", "")).strip()
            file_platform_id = guessed or None
        if file_platform_id is None:
            raise ValueError("platform_id is required in function args or payload")
        if file_platform_id not in self.adapters:
            raise KeyError(f"platform_id {file_platform_id!r} has no registered adapter")

        frames = self.load_platform_state_records(
            file_platform_id,
            raw_states,
        )
        return frames

    def load_platform_state_records(
        self,
        platform_id: str,
        records: Iterable[dict[str, Any]],
    ) -> list[ReplayFrame]:
        """Load in-memory platform state records."""

        if platform_id not in self.adapters:
            raise KeyError(f"platform_id {platform_id!r} has no registered adapter")
        parsed_records = list(records)
        if not parsed_records:
            raise ValueError("records must not be empty")

        first_timestamp: datetime | None = None
        frames: list[ReplayFrame] = []
        for idx, item in enumerate(parsed_records):
            if not isinstance(item, dict):
                raise ValueError("each telemetry record must be a dictionary")
            item_platform = str(item.get("platform_id", platform_id)).strip() or platform_id
            if item_platform != platform_id:
                raise ValueError(
                    f"record platform_id mismatch: expected {platform_id!r}, got {item_platform!r}"
                )
            state = _platform_state_from_record(item, platform_id=platform_id)
            sim_time_s, first_timestamp = _extract_sim_time(item, idx, first_timestamp)
            metadata = dict(item.get("metadata", {}))
            frames.append(
                ReplayFrame(
                    platform_id=platform_id,
                    sim_time_s=sim_time_s,
                    state=state,
                    metadata=metadata,
                )
            )

        frames.sort(key=lambda frame: frame.sim_time_s)
        self._frames_by_platform[platform_id] = frames
        return list(frames)

    def clear_loaded_sequences(self) -> None:
        """Drop all loaded replay timelines."""
        self._frames_by_platform.clear()

    def replay(
        self,
        *,
        time_scale: int = 1,
        synchronized: bool = True,
        realtime: bool = False,
        fault_injector: Any | None = None,
        aar_recorder: Any | None = None,
        track_store: Any | None = None,
        on_state_injected: Callable[[str, PlatformState, float], None] | None = None,
    ) -> ReplaySummary:
        """Replay loaded timelines into adapters via inject_simulated_telemetry."""

        if time_scale not in SUPPORTED_TIME_SCALES:
            raise ValueError(f"time_scale must be one of {SUPPORTED_TIME_SCALES}")
        if not self._frames_by_platform:
            raise RuntimeError("no platform telemetry loaded")

        events = self._build_event_timeline(synchronized=synchronized)
        latest_states: dict[str, PlatformState] = {}
        fault_events: list[dict[str, Any]] = []
        injected_count = 0
        self._injection_log = []
        wall_start = time.monotonic()
        previous_sim_time: float | None = None

        for frame in events:
            if realtime and previous_sim_time is not None:
                sim_gap = max(0.0, frame.sim_time_s - previous_sim_time)
                self._sleep_fn(sim_gap / float(time_scale))
            previous_sim_time = frame.sim_time_s

            state = copy.deepcopy(frame.state)
            latest_states[frame.platform_id] = state

            if fault_injector is not None:
                new_faults = fault_injector.run_scheduled_injections(
                    sim_time_s=frame.sim_time_s,
                    adapters=self.adapters,
                    platform_states=latest_states,
                    track_store=track_store,
                )
                fault_events.extend(new_faults)
                if aar_recorder is not None:
                    for event in new_faults:
                        aar_recorder.record_fault(event.get("fault_type", "unknown"), event)
                state = fault_injector.apply_active_effects(
                    platform_id=frame.platform_id,
                    state=state,
                    sim_time_s=frame.sim_time_s,
                )
                latest_states[frame.platform_id] = state

            adapter = self.adapters[frame.platform_id]
            injected_ok = bool(adapter.inject_simulated_telemetry(state))
            if injected_ok:
                injected_count += 1

            log_entry = {
                "platform_id": frame.platform_id,
                "sim_time_s": frame.sim_time_s,
                "position": tuple(state.position),
                "injected": injected_ok,
            }
            self._injection_log.append(log_entry)
            if aar_recorder is not None:
                aar_recorder.record_mission_event(
                    "telemetry_replayed",
                    {
                        "platform_id": frame.platform_id,
                        "sim_time_s": frame.sim_time_s,
                        "position": list(state.position),
                        "injected": injected_ok,
                    },
                )
            if on_state_injected is not None:
                on_state_injected(frame.platform_id, state, frame.sim_time_s)

        wall_duration = max(0.0, time.monotonic() - wall_start)
        sim_duration = max(0.0, events[-1].sim_time_s - events[0].sim_time_s) if len(events) > 1 else 0.0
        return ReplaySummary(
            platform_ids=sorted(self._frames_by_platform.keys()),
            frame_count=len(events),
            injected_count=injected_count,
            wall_duration_s=wall_duration,
            sim_duration_s=sim_duration,
            time_scale=time_scale,
            synchronized=synchronized,
            fault_events=fault_events,
            injection_log=list(self._injection_log),
        )

    def _build_event_timeline(self, *, synchronized: bool) -> list[ReplayFrame]:
        if synchronized:
            merged = [frame for frames in self._frames_by_platform.values() for frame in frames]
            merged.sort(key=lambda frame: (frame.sim_time_s, frame.platform_id))
            return merged

        ordered: list[ReplayFrame] = []
        for platform_id in sorted(self._frames_by_platform.keys()):
            ordered.extend(self._frames_by_platform[platform_id])
        return ordered

    def _install_injection_shims(self) -> None:
        for adapter in self.adapters.values():
            if callable(getattr(adapter, "inject_simulated_telemetry", None)):
                continue

            def _inject_simulated_telemetry(instance: Any, state: PlatformState) -> bool:
                # Tactical context: this shim emulates an adapter telemetry ingress
                # path so closed-range rehearsals can replay sensor/state updates.
                if hasattr(instance, "_position"):
                    instance._position = tuple(state.position)
                if hasattr(instance, "platform_id"):
                    instance.platform_id = state.platform_id
                if hasattr(state, "comms_status"):
                    setattr(instance, "comms_status", getattr(state, "comms_status"))
                if hasattr(state, "disabled_sensors"):
                    setattr(instance, "disabled_sensors", set(getattr(state, "disabled_sensors")))
                setattr(instance, "_last_simulated_state", state)
                return True

            setattr(adapter, "inject_simulated_telemetry", MethodType(_inject_simulated_telemetry, adapter))


def _extract_sim_time(
    record: MutableMapping[str, Any],
    idx: int,
    first_timestamp: datetime | None,
) -> tuple[float, datetime | None]:
    if "sim_time_s" in record:
        return float(record["sim_time_s"]), first_timestamp

    if "timestamp" in record:
        stamp = datetime.fromisoformat(str(record["timestamp"]).replace("Z", "+00:00"))
        if first_timestamp is None:
            first_timestamp = stamp
        return max(0.0, (stamp - first_timestamp).total_seconds()), first_timestamp

    return float(idx), first_timestamp


def _platform_state_from_record(record: Mapping[str, Any], *, platform_id: str) -> PlatformState:
    platform_type_raw = str(record.get("platform_type", "ugv")).strip().lower()
    try:
        platform_type = PlatformType(platform_type_raw)
    except ValueError:
        platform_type = PlatformType.UGV

    health_raw = str(record.get("health_state", HealthState.NOMINAL.value)).strip().lower()
    try:
        health_state = HealthState(health_raw)
    except ValueError:
        health_state = HealthState.NOMINAL

    autonomy_raw = str(record.get("autonomy_mode", AutonomyMode.SUPERVISED.value)).strip().lower()
    try:
        autonomy_mode = AutonomyMode(autonomy_raw)
    except ValueError:
        autonomy_mode = AutonomyMode.SUPERVISED

    position_raw = record.get("position", (0.0, 0.0, 0.0))
    if isinstance(position_raw, list):
        position_raw = tuple(position_raw)
    if not isinstance(position_raw, tuple) or len(position_raw) != 3:
        raise ValueError("position must be a 3-element tuple/list")

    state = PlatformState(
        platform_id=platform_id,
        platform_type=platform_type,
        position=position_raw,
        health_state=health_state,
        autonomy_mode=autonomy_mode,
    )

    # Tactical context: supplemental fields let fault-injection and AAR
    # pipelines carry comms/sensor state without changing base adapter contracts.
    if "comms_status" in record:
        setattr(state, "comms_status", str(record["comms_status"]))
    if "disabled_sensors" in record:
        setattr(state, "disabled_sensors", set(record.get("disabled_sensors", [])))
    if "gps_truth_position" in record:
        raw_truth = record.get("gps_truth_position")
        if isinstance(raw_truth, list):
            raw_truth = tuple(raw_truth)
        setattr(state, "gps_truth_position", raw_truth)
    return state
