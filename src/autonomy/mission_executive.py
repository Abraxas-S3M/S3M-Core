"""Mission executive for tactical mission phase management."""

from __future__ import annotations

from dataclasses import dataclass
import math

from src.platforms.common import MissionTask, MissionTaskType, MobilityCommand, MobilityCommandType, PlatformState


@dataclass
class MissionPhase:
    """Simple mission phase marker for patrol execution."""

    name: str


class MissionExecutive:
    """Lightweight mission lifecycle manager for PATROL task smoke testing."""

    def __init__(self, waypoint_tolerance_m: float = 50.0) -> None:
        self.waypoint_tolerance_m = waypoint_tolerance_m
        self.current_task: MissionTask | None = None
        self._is_active = False
        self._phase = MissionPhase("idle")
        self._next_waypoint_idx = 0

    @property
    def is_active(self) -> bool:
        return self._is_active

    @property
    def phase(self) -> str:
        return self._phase.name

    def start_mission(self, task: MissionTask) -> bool:
        if task.task_type != MissionTaskType.PATROL:
            return False
        if not task.waypoints:
            return False
        self.current_task = task
        self._is_active = True
        self._phase = MissionPhase("staging")
        self._next_waypoint_idx = 0
        return True

    def update(self, platform_state: PlatformState) -> list[MobilityCommand]:
        if not self._is_active or self.current_task is None:
            return []

        target = self.current_task.waypoints[self._next_waypoint_idx]
        if self._distance(platform_state.position, target) <= self.waypoint_tolerance_m:
            self._next_waypoint_idx = (self._next_waypoint_idx + 1) % len(self.current_task.waypoints)
            target = self.current_task.waypoints[self._next_waypoint_idx]
            self._phase = MissionPhase("on-station")
        else:
            self._phase = MissionPhase("transit")

        return [MobilityCommand(command_type=MobilityCommandType.MOVE_TO, target_position=target)]

    @staticmethod
    def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
        return math.dist(a, b)
