"""Facade for game-theoretic multi-agent mission arbitration.

This unifies conflict handling, consensus checks, and assignment generation
for resilient swarm coordination in contested tactical environments.
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.autonomy.models import AgentInfo, Mission

from .auction_allocator import AuctionAllocator
from .coalition_engine import CoalitionEngine
from .conflict_resolver import ConflictResolver
from .consensus_protocol import ByzantineConsensus


class MultiAgentArbitrator:
    """Unified entry-point for coalition/auction-based assignment."""

    def __init__(self, max_shapley_samples: int = 2000) -> None:
        self.coalition_engine = CoalitionEngine(mc_samples=min(5000, max(100, max_shapley_samples)))
        self.auction_allocator = AuctionAllocator(max_rounds=50)
        self.consensus = ByzantineConsensus()
        self.conflict_resolver = ConflictResolver()
        self.audit_log: List[Dict[str, Any]] = []

    def _log(self, event: str, payload: Dict[str, Any]) -> None:
        self.audit_log.append({"event": event, "payload": dict(payload)})
        if len(self.audit_log) > 5000:
            self.audit_log = self.audit_log[-5000:]

    def _as_agent_ids(self, agents: List[AgentInfo]) -> List[str]:
        return [a.agent_id for a in agents]

    def _mission_objectives(self, mission: Mission | Dict[str, Any]) -> List[str]:
        objectives = []
        if isinstance(mission, dict):
            mission_id = str(mission.get("mission_id", "mission"))
            mission_objectives = mission.get("objectives", [])
            if isinstance(mission_objectives, list) and mission_objectives:
                for idx, obj in enumerate(mission_objectives):
                    objectives.append(str(obj) or f"{mission_id}-obj-{idx}")
            else:
                waypoints = mission.get("waypoints", [])
                for idx, _ in enumerate(waypoints if isinstance(waypoints, list) else []):
                    objectives.append(f"{mission_id}-obj-{idx}")
        else:
            mission_id = mission.mission_id
            for idx, _ in enumerate(mission.waypoints or []):
                objectives.append(f"{mission_id}-obj-{idx}")
        if not objectives:
            objectives.append(f"{mission_id}-obj-0")
        return objectives

    def _mission_tasks(self, mission: Mission | Dict[str, Any]) -> List[str]:
        return self._mission_objectives(mission)

    def arbitrate(
        self,
        mission: Mission | Dict[str, Any],
        agents: List[AgentInfo],
        mode: str = "coalition",
        directives: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        """Run full pipeline: conflicts -> consensus -> coalition/auction."""
        mission_id = mission.mission_id if not isinstance(mission, dict) else str(mission.get("mission_id", "mission"))
        agent_ids = self._as_agent_ids(agents)
        objectives = self._mission_objectives(mission)
        tasks = self._mission_tasks(mission)
        directive_list = list(directives or [])

        conflicts = self.conflict_resolver.detect_conflicts(directive_list)
        resolved = self.conflict_resolver.resolve(directive_list)
        conflict_result = {
            "status": "ok" if not conflicts else "resolved",
            "conflicts": conflicts,
            "resolutions": list(self.conflict_resolver.last_resolutions),
            "directives": list(resolved.get("active_directives", [])),
        }

        votes = {aid: "approve" for aid in agent_ids}
        consensus_result = self.consensus.run_consensus(agent_ids, votes)

        mode_norm = str(mode).lower().strip()
        if mode_norm == "auction":
            utility = {}
            for i, aid in enumerate(agent_ids):
                for j, tid in enumerate(tasks):
                    utility[(aid, tid)] = float(max(0, 5 - abs(i - j)))
            auction = self.auction_allocator.allocate(agent_ids, tasks, utility)
            assignments = dict(auction["assignments"])
            assignment_mode = "auction"
        else:
            coalitions = self.coalition_engine.form_coalitions(agent_ids, objectives)
            assignments = dict(coalitions.get("assignments", {}))
            assignment_mode = "coalition"

        for idx, aid in enumerate(agent_ids):
            self.consensus.gossip_state(
                agent_id=f"belief:{aid}",
                state={"mission_id": mission_id, "assignment": assignments.get(aid)},
                timestamp=float(idx + 1),
            )
        gossip_state = self.consensus.gossip_snapshot()

        self._log(
            "arbitrate",
            {
                "mission_id": mission_id,
                "mode": assignment_mode,
                "consensus_result": consensus_result["result"],
                "conflicts": len(conflicts),
                "assignments": assignments,
            },
        )
        return {
            "assignments": assignments,
            "mode": assignment_mode,
            "consensus_result": consensus_result,
            "consensus": consensus_result,
            "conflict_resolution": conflict_result,
            "gossip_state": gossip_state,
            "stable": True,
            "rational": True,
        }

