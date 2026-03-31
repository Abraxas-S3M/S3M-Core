"""Composable reward functions for tactical autonomy training.

Each reward component captures a military objective such as mission completion,
survivability, formation discipline, or rules-of-engagement compliance.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, Tuple


def mission_completion_reward(distance_to_objective: float, threshold: float = 10.0) -> float:
    """Reward closing on objective because rapid objective capture reduces exposure."""
    distance = max(0.0, float(distance_to_objective))
    if distance <= threshold:
        return 100.0
    return max(0.0, 25.0 - (distance - threshold) * 0.25)


def threat_avoidance_reward(distance_to_nearest_threat: float, safe_distance: float = 50.0) -> float:
    """Reward maintaining standoff range to preserve platform survivability."""
    distance = max(0.0, float(distance_to_nearest_threat))
    if distance >= safe_distance:
        return 15.0
    if distance <= 1.0:
        return -50.0
    ratio = distance / safe_distance
    return -20.0 + 35.0 * ratio


def formation_cohesion_reward(
    agent_positions: Dict[str, Tuple[float, float, float]],
    target_spacing: float = 20.0,
) -> float:
    """Reward formation discipline to reduce fratricide and improve coverage."""
    if len(agent_positions) < 2:
        return 0.0
    coords = list(agent_positions.values())
    dists = []
    for i in range(len(coords)):
        for j in range(i + 1, len(coords)):
            dists.append(math.dist(coords[i], coords[j]))
    if not dists:
        return 0.0
    avg_dist = sum(dists) / len(dists)
    err = abs(avg_dist - target_spacing)
    return max(-20.0, 20.0 - err)


def efficiency_reward(steps_taken: int, max_steps: int) -> float:
    """Penalize long engagements because prolonged missions increase operational risk."""
    if max_steps <= 0:
        return -10.0
    ratio = min(1.0, max(0.0, float(steps_taken) / float(max_steps)))
    return 10.0 * (1.0 - ratio) - 5.0 * ratio


def rules_of_engagement_reward(action: int | str, roe_mode: str) -> float:
    """Enforce tactical ROE by penalizing unauthorized engagement behavior."""
    normalized_roe = str(roe_mode or "").lower()
    normalized_action = str(action).lower()
    is_engage = normalized_action in {"5", "engage"}
    if normalized_roe == "weapons_hold" and is_engage:
        return -100.0
    if normalized_roe == "weapons_tight" and is_engage:
        return -10.0
    if normalized_roe == "weapons_free" and is_engage:
        return 5.0
    return 0.0


def battery_conservation_reward(battery_pct: float) -> float:
    """Penalize low battery to preserve loiter margin for safe extraction."""
    battery = max(0.0, min(100.0, float(battery_pct)))
    if battery >= 30.0:
        return 5.0
    deficit = 30.0 - battery
    return -deficit * 0.8


def composite_reward(components: Dict[str, float], weights: Dict[str, float]) -> float:
    """Weighted sum for mission-specific tactical objective balancing."""
    total = 0.0
    for key, value in components.items():
        total += float(value) * float(weights.get(key, 1.0))
    return total

