"""Contract Net negotiation for resilient swarm mission assignment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from src.autonomy.models import AgentInfo, AgentRole, Mission


@dataclass(frozen=True)
class ContractBid:
    """Bid submitted by an agent candidate during mission negotiation."""

    agent_id: str
    score: float
    proposed_role: str
    rationale: str


class ContractNetProtocol:
    """
    Lightweight Contract Net protocol for tactical multi-agent negotiation.

    The implementation is deterministic so operators can audit assignment
    choices in contested or disconnected environments.
    """

    def __init__(self) -> None:
        self.last_bids: List[ContractBid] = []
        self.negotiation_log: List[Dict[str, object]] = []

    def negotiate(
        self,
        mission: Mission,
        available_agents: List[AgentInfo],
        scorer: Optional[Callable[[AgentInfo, Mission], float]] = None,
    ) -> Dict[str, str]:
        """
        Negotiate role assignment and return `{agent_id: role}` map.

        The scorer callback enables reuse of mission-domain tactical scoring
        from upstream allocators while preserving Contract Net semantics.
        """
        if mission is None:
            raise ValueError("mission is required")

        candidates = [agent for agent in available_agents if agent.is_available()]
        if not candidates:
            self.last_bids = []
            self._log(mission_id=mission.mission_id, bids=[], assignments={})
            return {}

        bids: List[ContractBid] = []
        for agent in candidates:
            score = self._bounded_score(
                scorer(agent, mission) if scorer is not None else self._default_score(agent, mission)
            )
            proposed_role = AgentRole.FOLLOWER.value
            rationale = "candidate scored by survivability, proximity, and payload fitness"
            bids.append(
                ContractBid(
                    agent_id=agent.agent_id,
                    score=score,
                    proposed_role=proposed_role,
                    rationale=rationale,
                )
            )

        bids.sort(key=lambda bid: (bid.score, bid.agent_id), reverse=True)
        self.last_bids = bids

        assignments: Dict[str, str] = {}
        leader = bids[0]
        assignments[leader.agent_id] = AgentRole.LEADER.value

        scout_bid = max(
            bids,
            key=lambda bid: len(self._agent_by_id(candidates, bid.agent_id).sensor_loadout),
        )
        assignments.setdefault(scout_bid.agent_id, AgentRole.SCOUT.value)

        for bid in bids:
            assignments.setdefault(bid.agent_id, AgentRole.FOLLOWER.value)

        self._log(
            mission_id=mission.mission_id,
            bids=[self._bid_to_dict(bid) for bid in bids],
            assignments=assignments,
        )
        return assignments

    def _default_score(self, agent: AgentInfo, mission: Mission) -> float:
        center = self._mission_center(mission)
        distance = agent.distance_to(*center)
        proximity_score = 1.0 / (1.0 + distance / 1000.0)
        battery_score = max(0.0, min(1.0, float(agent.battery_pct) / 100.0))
        payload_score = min(1.0, len(agent.sensor_loadout) / 4.0)
        return (0.50 * proximity_score) + (0.35 * battery_score) + (0.15 * payload_score)

    @staticmethod
    def _mission_center(mission: Mission) -> tuple[float, float, float]:
        if mission.waypoints:
            xs = [point[0] for point in mission.waypoints]
            ys = [point[1] for point in mission.waypoints]
            zs = [point[2] for point in mission.waypoints]
            return (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
        return (0.0, 0.0, 0.0)

    @staticmethod
    def _bounded_score(score: float) -> float:
        try:
            return max(0.0, min(1.0, float(score)))
        except Exception:
            return 0.0

    @staticmethod
    def _agent_by_id(agents: List[AgentInfo], agent_id: str) -> AgentInfo:
        for agent in agents:
            if agent.agent_id == agent_id:
                return agent
        raise KeyError(f"unknown agent_id: {agent_id}")

    @staticmethod
    def _bid_to_dict(bid: ContractBid) -> Dict[str, object]:
        return {
            "agent_id": bid.agent_id,
            "score": bid.score,
            "proposed_role": bid.proposed_role,
            "rationale": bid.rationale,
        }

    def _log(
        self,
        mission_id: str,
        bids: List[Dict[str, object]],
        assignments: Dict[str, str],
    ) -> None:
        self.negotiation_log.append(
            {
                "mission_id": mission_id,
                "bids": bids,
                "assignments": dict(assignments),
            }
        )
        if len(self.negotiation_log) > 2000:
            self.negotiation_log = self.negotiation_log[-2000:]
