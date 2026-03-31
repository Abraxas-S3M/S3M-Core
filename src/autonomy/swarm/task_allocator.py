"""Task allocation for tactical swarm missions.

Allocates mission roles using capability filters, survivability constraints, and
mission-area proximity so the most suitable platforms are assigned first.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

from src.autonomy.models import (
    AgentInfo,
    AgentRole,
    AgentCapability,
    Mission,
    MissionType,
    DecisionType,
    AutonomyDecision,
)


class TaskAllocator:
    """Allocates and reallocates swarm roles with explainable scoring."""

    def __init__(self) -> None:
        self.allocation_log: List[Dict[str, object]] = []

    def _mission_area_center(self, mission: Mission) -> Tuple[float, float, float]:
        if mission.waypoints:
            xs = [wp[0] for wp in mission.waypoints]
            ys = [wp[1] for wp in mission.waypoints]
            zs = [wp[2] for wp in mission.waypoints]
            return (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
        area = mission.parameters.get("mission_area")
        if isinstance(area, (list, tuple)) and len(area) == 3:
            return (float(area[0]), float(area[1]), float(area[2]))
        return (0.0, 0.0, 0.0)

    def _required_capability(self, mission: Mission) -> AgentCapability | None:
        mapping = {
            MissionType.PATROL: AgentCapability.AIR,
            MissionType.RECON: AgentCapability.AIR,
            MissionType.INTERCEPT: AgentCapability.AIR,
            MissionType.ESCORT: AgentCapability.AIR,
            MissionType.STRIKE: AgentCapability.AIR,
            MissionType.HOLD_POSITION: AgentCapability.GROUND,
            MissionType.SEARCH_AND_RESCUE: AgentCapability.AIR,
            MissionType.RETURN_TO_BASE: None,
            MissionType.CUSTOM: None,
        }
        override = mission.parameters.get("required_capability")
        if override:
            try:
                return AgentCapability(str(override))
            except Exception:
                pass
        return mapping.get(mission.mission_type)

    def score_agent(self, agent: AgentInfo, mission: Mission) -> float:
        """Return normalized 0-1 suitability score for mission assignment."""
        center = self._mission_area_center(mission)
        distance = agent.distance_to(*center)
        proximity_score = 1.0 / (1.0 + distance / 1000.0)
        battery_score = max(0.0, min(1.0, agent.battery_pct / 100.0))
        sensor_requirements = mission.parameters.get("required_sensors", [])
        if isinstance(sensor_requirements, str):
            sensor_requirements = [sensor_requirements]
        sensor_requirements = [str(x).lower() for x in sensor_requirements]
        if sensor_requirements:
            matches = sum(1 for s in agent.sensor_loadout if str(s).lower() in sensor_requirements)
            sensor_score = matches / len(sensor_requirements)
        else:
            sensor_score = 0.5
        score = (0.45 * proximity_score) + (0.35 * battery_score) + (0.20 * sensor_score)
        return max(0.0, min(1.0, score))

    def allocate(self, mission: Mission, available_agents: List[AgentInfo]) -> Dict[str, str]:
        """Allocate mission roles and return `{agent_id: role}`."""
        required_capability = self._required_capability(mission)
        candidates = [
            a
            for a in available_agents
            if a.is_available() and (required_capability is None or a.capability == required_capability)
        ]
        scored = sorted(
            [(a, self.score_agent(a, mission)) for a in candidates],
            key=lambda item: item[1],
            reverse=True,
        )

        assignments: Dict[str, str] = {}
        if not scored:
            mission.parameters["understaffed"] = True
            self.allocation_log.append(
                {
                    "mission_id": mission.mission_id,
                    "reason": "No available capable agents",
                    "assignments": {},
                }
            )
            return assignments

        # Tactical assignment: best overall platform leads.
        leader = scored[0][0]
        assignments[leader.agent_id] = AgentRole.LEADER.value

        if len(scored) > 1:
            assignments[scored[1][0].agent_id] = AgentRole.FOLLOWER.value

        sensor_best = max(scored, key=lambda item: len(item[0].sensor_loadout))[0]
        assignments.setdefault(sensor_best.agent_id, AgentRole.SCOUT.value)

        for candidate, _ in scored[2:]:
            assignments.setdefault(candidate.agent_id, AgentRole.FOLLOWER.value)

        needed = int(mission.parameters.get("min_agents", 3))
        if len(assignments) < needed:
            mission.parameters["understaffed"] = True

        mission.assigned_agents = list(assignments.keys())
        self.allocation_log.append(
            {
                "mission_id": mission.mission_id,
                "required_capability": required_capability.value if required_capability else "any",
                "scores": {agent.agent_id: score for agent, score in scored},
                "assignments": assignments,
                "understaffed": mission.parameters.get("understaffed", False),
            }
        )
        decision_log = mission.parameters.get("decision_log")
        if isinstance(decision_log, list):
            decision_log.append(
                AutonomyDecision(
                    decision_id=f"alloc-{mission.mission_id}-{len(self.allocation_log)}",
                    timestamp=mission.created_at,
                    decision_type=DecisionType.DELEGATE,
                    agent_id=leader.agent_id,
                    mission_id=mission.mission_id,
                    context={"required_capability": required_capability.value if required_capability else "any"},
                    action_taken={"assignments": assignments},
                    alternatives_considered=[],
                    confidence=0.8,
                    reasoning="Task allocation selected leader/follower/scout roles by tactical score.",
                    llm_consulted=False,
                    requires_human_review=False,
                    risk_score=0.2,
                )
            )
        return assignments

    def reallocate(self, mission: Mission, agents: List[AgentInfo], lost_agent_id: str) -> Dict[str, str]:
        """Reassign roles after agent loss and record rationale."""
        mission.assigned_agents = [agent_id for agent_id in mission.assigned_agents if agent_id != lost_agent_id]
        available = [a for a in agents if a.agent_id != lost_agent_id]
        assignments = self.allocate(mission, available)
        self.allocation_log.append(
            {
                "mission_id": mission.mission_id,
                "event": "reallocate",
                "lost_agent_id": lost_agent_id,
                "assignments": assignments,
            }
        )
        return assignments
