"""Adapter from interceptor guidance output to AutopilotBridge commands.

Military context:
Converts high-rate command-guidance vectors into practical MOVE_TO commands so
fielded autopilot links can execute intercept geometry without custom firmware.
"""

from __future__ import annotations

from math import sqrt
from typing import Any, Dict, Tuple

from services.interceptor.models import GuidancePhase, GuidanceSolution, SteeringCommand

Vector3 = Tuple[float, float, float]


def _vector_norm(v: Vector3) -> float:
    return sqrt((v[0] * v[0]) + (v[1] * v[1]) + (v[2] * v[2]))


class AutopilotAdapter:
    """Translate guidance commands into AutopilotBridge-compatible payloads."""

    def __init__(self, command_horizon_s: float = 1.0, min_move_distance_m: float = 2.0) -> None:
        self.command_horizon_s = max(0.1, float(command_horizon_s))
        self.min_move_distance_m = max(0.5, float(min_move_distance_m))

    def steering_to_waypoint(self, current_position_m: Vector3, steering: SteeringCommand) -> Vector3:
        desired_velocity = steering.desired_velocity_mps
        projected = (
            current_position_m[0] + (desired_velocity[0] * self.command_horizon_s),
            current_position_m[1] + (desired_velocity[1] * self.command_horizon_s),
            current_position_m[2] + (desired_velocity[2] * self.command_horizon_s),
        )
        if projected[2] < 0.0:
            projected = (projected[0], projected[1], 0.0)
        return projected

    def solution_to_command(self, current_position_m: Vector3, solution: GuidanceSolution) -> Dict[str, Any]:
        if solution.phase in {GuidancePhase.PRELAUNCH, GuidancePhase.ENGAGED, GuidancePhase.MISS}:
            return {"type": "HOLD"}

        waypoint = self.steering_to_waypoint(current_position_m, solution.steering_command)
        move_distance = _vector_norm(
            (
                waypoint[0] - current_position_m[0],
                waypoint[1] - current_position_m[1],
                waypoint[2] - current_position_m[2],
            )
        )
        if move_distance < self.min_move_distance_m:
            return {"type": "HOLD"}
        return {
            "type": "MOVE_TO",
            "position": waypoint,
            "metadata": {
                "phase": solution.phase.value,
                "mode": solution.mode.value,
                "target_id": solution.target_id,
                "reason": solution.reason,
            },
        }

    def send_solution(self, autopilot: Any, current_position_m: Vector3, solution: GuidanceSolution) -> bool:
        command = self.solution_to_command(current_position_m, solution)
        return bool(autopilot.send_command(command))
