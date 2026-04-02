"""
Python model checker for S3M ROE invariants.
Runs without TLA+ toolbox — useful in CI/pre-commit gates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import FrozenSet, List, Optional, Tuple

logger = logging.getLogger("s3m.roe.checker")

SUBSYSTEMS = {"autonomy", "threat_detection", "cyber"}
HUMAN_OPERATORS = {"commander", "operator"}


@dataclass(frozen=True)
class ROEState:
    pending: FrozenSet[Tuple[str, int]]  # (subsystem, ticket_id)
    granted: FrozenSet[int]  # ticket_ids
    lethal_count: int
    audit_len: int


def initial_state() -> ROEState:
    return ROEState(
        pending=frozenset(),
        granted=frozenset(),
        lethal_count=0,
        audit_len=0,
    )


def successors(state: ROEState, max_ticket: int = 3) -> List[ROEState]:
    nexts: List[ROEState] = []

    # RequestApproval
    for sys in SUBSYSTEMS:
        for tid in range(1, max_ticket + 1):
            if (sys, tid) not in state.pending:
                nexts.append(
                    ROEState(
                        pending=state.pending | {(sys, tid)},
                        granted=state.granted,
                        lethal_count=state.lethal_count,
                        audit_len=state.audit_len + 1,
                    )
                )

    # GrantApproval (only human operators)
    for sys, tid in state.pending:
        if tid not in state.granted:
            nexts.append(
                ROEState(
                    pending=state.pending,
                    granted=state.granted | {tid},
                    lethal_count=state.lethal_count,
                    audit_len=state.audit_len + 1,
                )
            )

    # ExecuteLethalAction
    for tid in state.granted:
        nexts.append(
            ROEState(
                pending=state.pending,
                granted=state.granted,
                lethal_count=state.lethal_count + 1,
                audit_len=state.audit_len + 1,
            )
        )

    return nexts


def check_invariants(state: ROEState) -> Optional[str]:
    if state.lethal_count > 0 and len(state.granted) == 0:
        return "VIOLATION: Lethal action without approval"
    if state.lethal_count > 0 and state.audit_len == 0:
        return "VIOLATION: Lethal action without audit entry"
    return None


def run_bfs(max_depth: int = 4, max_ticket: int = 3) -> bool:
    visited = {initial_state()}
    frontier = [initial_state()]
    violations = []

    for depth in range(max_depth):
        next_frontier = []
        for state in frontier:
            violation = check_invariants(state)
            if violation:
                violations.append((state, violation))
            for s in successors(state, max_ticket):
                if s not in visited:
                    visited.add(s)
                    next_frontier.append(s)
        frontier = next_frontier
        logger.info("Depth %d: %d states explored", depth + 1, len(visited))

    if violations:
        for state, msg in violations:
            logger.error("❌ %s — state: %s", msg, state)
        return False

    logger.info("✅ All ROE invariants satisfied across %d states", len(visited))
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    ok = run_bfs(max_depth=5)
    raise SystemExit(0 if ok else 1)
