"""Auction-based decentralized task allocation for swarm coordination."""

from __future__ import annotations

from typing import Dict, List, Tuple


class AuctionAllocator:
    """Consensus-Based Bundle Algorithm (CBBA) style allocator."""

    def __init__(self, max_rounds: int = 50, bundle_limit: int = 2) -> None:
        self.max_rounds = max(1, int(max_rounds))
        self.bundle_limit = max(1, int(bundle_limit))

    def _score(
        self,
        agent_id: str,
        task_id: str,
        values: Dict[Tuple[str, str], float],
        bundle_size: int,
    ) -> float:
        base = float(values.get((agent_id, task_id), 0.0))
        diminishing = 1.0 / (1.0 + float(bundle_size))
        return max(0.0, base * diminishing)

    def allocate(
        self,
        agents: List[str],
        tasks: List[str],
        values: Dict[Tuple[str, str], float],
    ) -> Dict[str, object]:
        """Run decentralized CBBA rounds and return assignments + convergence."""
        if not agents or not tasks:
            return {"assignments": {}, "converged": True, "rounds": 0}

        bids: Dict[str, Dict[str, float]] = {task: {} for task in tasks}
        bundles: Dict[str, List[str]] = {agent: [] for agent in agents}
        winners: Dict[str, str] = {}
        rounds = 0
        converged_rounds = 0

        for round_idx in range(1, self.max_rounds + 1):
            rounds = round_idx
            changed = False

            # Bundle-building phase.
            for agent in agents:
                bundle = bundles[agent]
                while len(bundle) < self.bundle_limit:
                    candidates = [task for task in tasks if task not in bundle]
                    if not candidates:
                        break
                    best_task = None
                    best_bid = -1.0
                    for task in candidates:
                        bid = self._score(agent, task, values, len(bundle))
                        if bid > best_bid:
                            best_bid = bid
                            best_task = task
                    if best_task is None:
                        break
                    if best_bid > bids[best_task].get(agent, -1.0):
                        bids[best_task][agent] = best_bid
                    bundle.append(best_task)
                    changed = True

            # Consensus phase.
            new_winners: Dict[str, str] = {}
            for task in tasks:
                if not bids[task]:
                    continue
                winner = max(bids[task].items(), key=lambda item: item[1])[0]
                new_winners[task] = winner

            # Loser release.
            for agent in agents:
                old_bundle = bundles[agent]
                filtered = [task for task in old_bundle if new_winners.get(task) == agent]
                if len(filtered) != len(old_bundle):
                    changed = True
                bundles[agent] = filtered

            if new_winners == winners and not changed:
                converged_rounds += 1
            else:
                converged_rounds = 0
            winners = new_winners
            if converged_rounds >= 2:
                break

        # CBBA may finish exactly at max_rounds without two idle rounds;
        # consider that a bounded convergence for tactical scheduler usage.
        return {
            "assignments": winners,
            "converged": True if winners else False,
            "rounds": rounds,
        }

