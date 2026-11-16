"""AutoHeal incident state machine (single transition table, exhaustively checked).

Military/tactical context:
An autonomous repair loop must never act without authorisation, never declare success
without verification, and never get stuck. The same table drives the runtime and the
model check (``check_model``), so the property checked is the property run.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Set, Tuple

TERMINAL = frozenset({"RESOLVED", "ROLLED_BACK", "ESCALATED", "CLOSED_NO_FAULT"})

TRANSITIONS: Dict[Tuple[str, str], str] = {
    ("DETECTED", "no_fault"): "CLOSED_NO_FAULT",
    ("DETECTED", "diagnosed"): "DIAGNOSED",
    ("DIAGNOSED", "planned"): "PLANNED",
    ("DIAGNOSED", "unrepairable"): "ESCALATED",
    ("PLANNED", "authorized"): "AUTHORIZED",
    ("PLANNED", "denied"): "ESCALATED",
    ("AUTHORIZED", "repair_started"): "REPAIRING",
    ("REPAIRING", "repairs_applied"): "VERIFYING",
    ("REPAIRING", "repair_failed"): "ROLLING_BACK",
    ("VERIFYING", "verified"): "RESOLVED",
    ("VERIFYING", "verification_failed"): "ROLLING_BACK",
    ("ROLLING_BACK", "restored"): "ROLLED_BACK",
    ("ROLLING_BACK", "rollback_failed"): "ESCALATED",
}
EVENTS = sorted({e for _, e in TRANSITIONS})


class IllegalTransition(RuntimeError):
    pass


@dataclass
class IncidentFSM:
    incident_id: str
    state: str = "DETECTED"
    history: List[Dict[str, str]] = field(default_factory=list)

    def fire(self, event: str, note: str = "") -> str:
        nxt = TRANSITIONS.get((self.state, event))
        if nxt is None:
            raise IllegalTransition(f"{self.incident_id}: {event!r} not allowed in {self.state}")
        self.history.append({"at": datetime.now(timezone.utc).isoformat(), "from": self.state,
                             "event": event, "to": nxt, "note": note[:200]})
        self.state = nxt
        return nxt

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL


def check_model(max_depth: int = 12) -> Dict[str, object]:
    """Exhaustive exploration of every event sequence from DETECTED.

    Safety (on every path): REPAIRING only after AUTHORIZED; RESOLVED only after VERIFYING;
    terminal states absorb all events. Liveness (structural): from every reachable state a
    terminal state is reachable; there are no cycles, so every run terminates.
    """
    violations: List[str] = []
    reachable: Set[str] = set()
    queue = deque([("DETECTED", ("DETECTED",))])
    paths = 0
    while queue:
        state, path = queue.popleft()
        reachable.add(state)
        if state in TERMINAL:
            paths += 1
            if any((state, e) in TRANSITIONS for e in EVENTS):
                violations.append(f"terminal {state} has outgoing transition")
            continue
        if len(path) > max_depth:
            violations.append(f"path exceeds depth (cycle?): {path}")
            continue
        for e in EVENTS:
            nxt = TRANSITIONS.get((state, e))
            if nxt is None:
                continue
            new = path + (nxt,)
            if nxt == "REPAIRING" and "AUTHORIZED" not in path:
                violations.append(f"REPAIRING without AUTHORIZED: {new}")
            if nxt == "RESOLVED" and "VERIFYING" not in path:
                violations.append(f"RESOLVED without VERIFYING: {new}")
            queue.append((nxt, new))
    # liveness: reverse reachability to terminals
    can_finish = set(TERMINAL)
    changed = True
    while changed:
        changed = False
        for (s, _), t in TRANSITIONS.items():
            if t in can_finish and s not in can_finish:
                can_finish.add(s)
                changed = True
    stuck = sorted(reachable - can_finish)
    if stuck:
        violations.append(f"states that cannot terminate: {stuck}")
    return {"states": sorted(reachable), "complete_paths": paths, "violations": violations, "ok": not violations}
