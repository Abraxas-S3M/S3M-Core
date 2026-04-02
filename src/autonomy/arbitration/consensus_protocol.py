"""Byzantine-tolerant consensus and gossip for swarm arbitration."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple


class ByzantineConsensus:
    """PBFT-inspired consensus with quorum and commander override."""

    def __init__(self) -> None:
        self._registered_nodes: List[str] = []
        self._vote_history: Dict[str, List[Tuple[str, str]]] = {}
        self._gossip_store: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def register_node(self, node_id: str) -> None:
        nid = str(node_id)
        if nid not in self._registered_nodes:
            self._registered_nodes.append(nid)

    def _quorum(self, n_nodes: int) -> int:
        return int(math.ceil((2.0 * n_nodes) / 3.0))

    def _detect_flip_flop(self, proposal_id: str, node_id: str, vote: str) -> bool:
        history = self._vote_history.setdefault(proposal_id, [])
        previous = [v for n, v in history if n == node_id]
        history.append((node_id, vote))
        return bool(previous) and previous[-1] != vote

    def run_consensus(
        self,
        nodes: Sequence[str],
        votes: Dict[str, str],
        commander_override: Optional[str] = None,
        proposal_id: str = "proposal",
    ) -> Dict[str, Any]:
        """Run prepare+commit style voting and return consensus outcome."""
        node_list = [str(n) for n in nodes]
        n_nodes = len(node_list)
        if n_nodes == 0:
            return {"result": "NO_QUORUM", "status": "NO_QUORUM", "approved": False}
        quorum = self._quorum(n_nodes)

        if commander_override:
            result = str(commander_override).upper().strip()
            approved = result == "APPROVE"
            return {
                "result": "APPROVE" if approved else "REJECT",
                "status": "COMMANDER_OVERRIDE",
                "approved": approved,
                "commander_override": True,
                "quorum": quorum,
            }

        approve_count = 0
        reject_count = 0
        byzantine_fault = False
        for node in node_list:
            raw_vote = str(votes.get(node, "reject")).lower().strip()
            vote = "approve" if raw_vote == "approve" else "reject"
            if self._detect_flip_flop(proposal_id, node, vote):
                byzantine_fault = True
            if vote == "approve":
                approve_count += 1
            else:
                reject_count += 1

        if byzantine_fault:
            return {
                "result": "REJECT",
                "status": "BYZANTINE_FAULT",
                "approved": False,
                "quorum": quorum,
                "approve_votes": approve_count,
                "reject_votes": reject_count,
            }
        if approve_count >= quorum:
            return {
                "result": "APPROVE",
                "status": "APPROVE",
                "approved": True,
                "quorum": quorum,
                "approve_votes": approve_count,
                "reject_votes": reject_count,
            }
        if reject_count >= quorum:
            return {
                "result": "REJECT",
                "status": "REJECT",
                "approved": False,
                "quorum": quorum,
                "approve_votes": approve_count,
                "reject_votes": reject_count,
            }
        return {
            "result": "REJECT",
            "status": "NO_QUORUM",
            "approved": False,
            "quorum": quorum,
            "approve_votes": approve_count,
            "reject_votes": reject_count,
        }

    def reach_consensus(self, proposal: Dict[str, Any], votes: Dict[str, bool]) -> Dict[str, Any]:
        """Adapter method used by coordinator/arbitrator integration."""
        node_list = self._registered_nodes[:] or [str(k) for k in votes.keys()]
        mapped_votes = {str(node): ("approve" if bool(votes.get(node, False)) else "reject") for node in node_list}
        proposal_id = str(proposal.get("mission_id", proposal.get("proposal_id", "proposal")))
        return self.run_consensus(node_list, mapped_votes, commander_override=None, proposal_id=proposal_id)

    def gossip_state(self, agent_id: str, state: Dict[str, Any], timestamp: float) -> None:
        """CRDT-like last-writer-wins gossip merge."""
        aid = str(agent_id)
        ts = float(timestamp)
        current = self._gossip_store.get(aid)
        if current is None or ts >= current[0]:
            self._gossip_store[aid] = (ts, dict(state))

    def gossip_snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {aid: dict(payload) for aid, (_, payload) in self._gossip_store.items()}

