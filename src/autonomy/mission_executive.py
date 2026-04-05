"""Mission executive for tactical mission phase management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any

from src.platforms.common import (
    MissionTask,
    MissionTaskType,
    MobilityCommand,
    MobilityCommandType,
    PlatformState,
    Track,
)


@dataclass
class MissionPhase:
    """Simple mission phase marker for patrol execution."""

    name: str


@dataclass
class SensorCommand:
    """Sensor tasking primitive for contested-area observation workflows."""

    command_type: str
    track_id: str | None = None
    target_position: tuple[float, float, float] | None = None


class MissionExecutive:
    """Lightweight mission lifecycle manager for PATROL task smoke testing."""

    def __init__(self, waypoint_tolerance_m: float = 50.0) -> None:
        self.waypoint_tolerance_m = waypoint_tolerance_m
        self.current_task: MissionTask | None = None
        self._is_active = False
        self._is_paused = False
        self._phase = MissionPhase("idle")
        self._next_waypoint_idx = 0
        self._phase_log: list[dict[str, Any]] = []

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    @property
    def phase(self) -> str:
        return self._phase.name

    @property
    def phase_log(self) -> list[dict[str, Any]]:
        return list(self._phase_log)

    def start_mission(self, task: MissionTask) -> bool:
        if task.task_type != MissionTaskType.PATROL:
            return False
        if not task.waypoints:
            return False
        self.current_task = task
        self._is_active = True
        self._is_paused = False
        self._next_waypoint_idx = 0
        self._set_phase("staging", reason="mission_start")
        return True

    def pause(self) -> bool:
        if not self._is_active or self._is_paused:
            return False
        self._is_paused = True
        self._set_phase("paused", reason="mission_pause")
        return True

    def resume(self) -> bool:
        if not self._is_active or not self._is_paused:
            return False
        self._is_paused = False
        # Resume to tactical transit phase while moving toward patrol objective.
        self._set_phase("transit", reason="mission_resume")
        return True

    def abort(self) -> bool:
        if not self._is_active:
            return False
        self._is_active = False
        self._is_paused = False
        self._set_phase("aborted", reason="mission_abort")
        return True

    def update(self, platform_state: PlatformState) -> list[MobilityCommand]:
        if not self._is_active or self.current_task is None:
            return []
        if self._is_paused:
            return []

        target = self.current_task.waypoints[self._next_waypoint_idx]
        if self._distance(platform_state.position, target) <= self.waypoint_tolerance_m:
            self._next_waypoint_idx = (self._next_waypoint_idx + 1) % len(self.current_task.waypoints)
            target = self.current_task.waypoints[self._next_waypoint_idx]
            self._set_phase("on-station", reason="waypoint_reached")
        else:
            self._set_phase("transit", reason="waypoint_transit")

        return [MobilityCommand(command_type=MobilityCommandType.MOVE_TO, target_position=target)]

    def tick(
        self,
        platform_state: PlatformState,
        tracks: list[Track] | None = None,
    ) -> tuple[list[MobilityCommand], list[SensorCommand]]:
        """Advance mission state and emit mobility/sensor directives.

        Tactical context:
        This fuses ownship navigation intent with local track awareness so
        operators can keep patrol movement and surveillance synchronized.
        """
        if not self._is_active or self._is_paused:
            return [], []
        mobility_commands = self.update(platform_state)
        sensor_commands = self._build_sensor_commands(tracks or [])
        return mobility_commands, sensor_commands

    def _set_phase(self, phase_name: str, reason: str) -> None:
        if self._phase.name == phase_name:
            return
        previous = self._phase.name
        self._phase = MissionPhase(phase_name)
        self._phase_log.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "from_phase": previous,
                "to_phase": phase_name,
                "reason": reason,
            }
        )
        if len(self._phase_log) > 1000:
            self._phase_log = self._phase_log[-1000:]

    def _build_sensor_commands(self, tracks: list[Track]) -> list[SensorCommand]:
        if not tracks:
            return []
        # Prioritize higher-confidence contacts first for tactical ISR continuity.
        prioritized = sorted(tracks, key=lambda track: track.confidence, reverse=True)
        return [
            SensorCommand(
                command_type="observe_track",
                track_id=track.track_id,
                target_position=track.position,
            )
            for track in prioritized[:3]
        ]

    @staticmethod
    def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        return math.dist(a, b)
