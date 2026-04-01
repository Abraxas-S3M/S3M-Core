"""DIS dead reckoning algorithms for network-efficient entity updates."""

from __future__ import annotations

import math
from typing import Dict


class DISDeadReckoning:
    """Implements basic DIS dead reckoning algorithms used in exercises."""

    def __init__(self):
        pass

    def extrapolate(self, entity_state: dict, dt_seconds: float, algorithm: int = 2) -> dict:
        state = dict(entity_state)
        position = dict(state.get("position", {}))
        velocity = dict(state.get("velocity", {}))
        orientation = dict(state.get("orientation", {}))
        acceleration = dict(state.get("acceleration", {}))
        angular_velocity = dict(state.get("angular_velocity", {}))
        dt = float(max(0.0, dt_seconds))

        if algorithm == 1:
            return state

        if algorithm == 2:
            position["x"] = float(position.get("x", 0.0)) + float(velocity.get("x", 0.0)) * dt
            position["y"] = float(position.get("y", 0.0)) + float(velocity.get("y", 0.0)) * dt
            position["z"] = float(position.get("z", 0.0)) + float(velocity.get("z", 0.0)) * dt
        elif algorithm == 3:
            position["x"] = float(position.get("x", 0.0)) + float(velocity.get("x", 0.0)) * dt
            position["y"] = float(position.get("y", 0.0)) + float(velocity.get("y", 0.0)) * dt
            position["z"] = float(position.get("z", 0.0)) + float(velocity.get("z", 0.0)) * dt
            orientation["psi"] = float(orientation.get("psi", 0.0)) + float(
                angular_velocity.get("psi", 0.0)
            ) * dt
            orientation["theta"] = float(orientation.get("theta", 0.0)) + float(
                angular_velocity.get("theta", 0.0)
            ) * dt
            orientation["phi"] = float(orientation.get("phi", 0.0)) + float(
                angular_velocity.get("phi", 0.0)
            ) * dt
        elif algorithm == 5:
            ax = float(acceleration.get("x", 0.0))
            ay = float(acceleration.get("y", 0.0))
            az = float(acceleration.get("z", 0.0))
            vx = float(velocity.get("x", 0.0))
            vy = float(velocity.get("y", 0.0))
            vz = float(velocity.get("z", 0.0))
            position["x"] = float(position.get("x", 0.0)) + vx * dt + 0.5 * ax * dt * dt
            position["y"] = float(position.get("y", 0.0)) + vy * dt + 0.5 * ay * dt * dt
            position["z"] = float(position.get("z", 0.0)) + vz * dt + 0.5 * az * dt * dt
            velocity["x"] = vx + ax * dt
            velocity["y"] = vy + ay * dt
            velocity["z"] = vz + az * dt
        else:
            position["x"] = float(position.get("x", 0.0)) + float(velocity.get("x", 0.0)) * dt
            position["y"] = float(position.get("y", 0.0)) + float(velocity.get("y", 0.0)) * dt
            position["z"] = float(position.get("z", 0.0)) + float(velocity.get("z", 0.0)) * dt

        state["position"] = position
        state["velocity"] = velocity
        state["orientation"] = orientation
        return state

    def should_update(
        self,
        current: dict,
        last_sent: dict,
        position_threshold_m: float = 1.0,
        orientation_threshold_rad: float = 0.05,
    ) -> bool:
        cur_pos = current.get("position", {})
        last_pos = last_sent.get("position", {})
        dx = float(cur_pos.get("x", 0.0)) - float(last_pos.get("x", 0.0))
        dy = float(cur_pos.get("y", 0.0)) - float(last_pos.get("y", 0.0))
        dz = float(cur_pos.get("z", 0.0)) - float(last_pos.get("z", 0.0))
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        if distance > float(position_threshold_m):
            return True

        cur_orient = current.get("orientation", {})
        last_orient = last_sent.get("orientation", {})
        dpsi = abs(float(cur_orient.get("psi", 0.0)) - float(last_orient.get("psi", 0.0)))
        dtheta = abs(float(cur_orient.get("theta", 0.0)) - float(last_orient.get("theta", 0.0)))
        dphi = abs(float(cur_orient.get("phi", 0.0)) - float(last_orient.get("phi", 0.0)))
        return max(dpsi, dtheta, dphi) > float(orientation_threshold_rad)
