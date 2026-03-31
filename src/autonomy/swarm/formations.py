"""Formation control utilities for tactical swarm maneuver.

Implements military formation geometries and smooth transitions so autonomous
agents can maintain coverage and deconfliction while maneuvering under threat.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

from src.autonomy.models import FormationType


class FormationController:
    """Computes and scores swarm formations for coordinated operations."""

    def compute_formation(
        self,
        formation_type: FormationType,
        leader_position: tuple,
        heading: float,
        n_agents: int,
        spacing: float,
    ) -> Dict[int, tuple]:
        """Return absolute station positions for all agents in formation."""
        if n_agents <= 0:
            return {}
        if len(leader_position) != 3:
            raise ValueError("leader_position must be 3D tuple")
        if spacing <= 0:
            raise ValueError("spacing must be positive")

        lx, ly, lz = (float(leader_position[0]), float(leader_position[1]), float(leader_position[2]))
        heading_rad = math.radians(float(heading) % 360.0)
        forward = (math.cos(heading_rad), math.sin(heading_rad))
        right = (-math.sin(heading_rad), math.cos(heading_rad))

        def project(offset_forward: float, offset_right: float) -> tuple:
            ox = forward[0] * offset_forward + right[0] * offset_right
            oy = forward[1] * offset_forward + right[1] * offset_right
            return (lx + ox, ly + oy, lz)

        positions: Dict[int, tuple] = {0: (lx, ly, lz)}
        for idx in range(1, n_agents):
            if formation_type == FormationType.LINE:
                side = -1 if idx % 2 == 0 else 1
                rank = (idx + 1) // 2
                positions[idx] = project(0.0, side * rank * spacing)
            elif formation_type == FormationType.WEDGE:
                side = -1 if idx % 2 == 0 else 1
                rank = (idx + 1) // 2
                positions[idx] = project(-rank * spacing, side * rank * spacing)
            elif formation_type == FormationType.DIAMOND:
                pattern = [
                    (-spacing, 0.0),
                    (-2 * spacing, spacing),
                    (-2 * spacing, -spacing),
                    (-3 * spacing, 0.0),
                ]
                rel = pattern[(idx - 1) % len(pattern)]
                positions[idx] = project(rel[0], rel[1])
            elif formation_type == FormationType.CIRCLE:
                angle = 2.0 * math.pi * idx / max(1, n_agents - 1)
                positions[idx] = (
                    lx + math.cos(angle) * spacing,
                    ly + math.sin(angle) * spacing,
                    lz,
                )
            elif formation_type == FormationType.ECHELON_LEFT:
                positions[idx] = project(-idx * spacing, -idx * spacing)
            elif formation_type == FormationType.ECHELON_RIGHT:
                positions[idx] = project(-idx * spacing, idx * spacing)
            elif formation_type == FormationType.COLUMN:
                positions[idx] = project(-idx * spacing, 0.0)
            elif formation_type == FormationType.SPREAD:
                side = -1 if idx % 2 == 0 else 1
                positions[idx] = project(-idx * spacing * 1.5, side * idx * spacing * 1.5)
            else:
                positions[idx] = project(-idx * spacing, 0.0)
        return positions

    def transition(
        self,
        current_positions: Dict[str, tuple],
        target_positions: Dict[str, tuple],
        step_fraction: float,
    ) -> Dict[str, tuple]:
        """Interpolate towards target formation for smooth tactical transitions."""
        alpha = max(0.0, min(1.0, float(step_fraction)))
        transitioned: Dict[str, tuple] = {}
        all_keys = set(current_positions) | set(target_positions)
        for aid in all_keys:
            cur = current_positions.get(aid, target_positions.get(aid, (0.0, 0.0, 0.0)))
            tgt = target_positions.get(aid, cur)
            transitioned[aid] = (
                float(cur[0]) + (float(tgt[0]) - float(cur[0])) * alpha,
                float(cur[1]) + (float(tgt[1]) - float(cur[1])) * alpha,
                float(cur[2]) + (float(tgt[2]) - float(cur[2])) * alpha,
            )
        return transitioned

    def formation_score(self, agent_positions: Dict[str, tuple], target_positions: Dict[str, tuple]) -> float:
        """Score 0..1 based on positional adherence to assigned formation stations."""
        if not target_positions:
            return 1.0
        total_error = 0.0
        matched = 0
        for aid, target in target_positions.items():
            if aid not in agent_positions:
                total_error += 50.0
                matched += 1
                continue
            actual = agent_positions[aid]
            total_error += math.dist(
                (float(actual[0]), float(actual[1]), float(actual[2])),
                (float(target[0]), float(target[1]), float(target[2])),
            )
            matched += 1
        if matched == 0:
            return 0.0
        avg_error = total_error / matched
        return max(0.0, min(1.0, 1.0 - (avg_error / 100.0)))
