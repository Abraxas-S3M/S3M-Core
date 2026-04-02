"""Directive conflict detection and resolution for tactical arbitration."""

from __future__ import annotations

from typing import Any, Dict, List


class ConflictResolver:
    """Detects and resolves mission directive conflicts."""

    def __init__(self) -> None:
        self.history: List[Dict[str, Any]] = []
        self.last_resolutions: List[Dict[str, Any]] = []

    def detect_conflicts(self, directives: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        conflicts: List[Dict[str, Any]] = []
        if not directives:
            return conflicts

        has_engage = any(
            str(d.get("type", d.get("action", ""))).lower() == "engage" for d in directives
        )
        has_weapons_hold = any(str(d.get("rules_of_engagement", "")).lower() == "weapons_hold" for d in directives)
        if has_engage and has_weapons_hold:
            conflicts.append({"type": "ROE_CONTRADICTION", "strategy": "priority_wins"})

        resources: Dict[str, int] = {}
        for directive in directives:
            resource = directive.get("resource")
            if resource:
                key = str(resource)
                resources[key] = resources.get(key, 0) + 1
        if any(count > 1 for count in resources.values()):
            conflicts.append({"type": "RESOURCE_CONTENTION", "strategy": "cost_benefit"})

        priorities = {int(d.get("priority", d.get("mission_priority", 3))) for d in directives}
        if len(priorities) > 1:
            conflicts.append({"type": "MISSION_PRIORITY", "strategy": "priority_wins"})

        if any(bool(d.get("self_preservation")) for d in directives):
            conflicts.append({"type": "SELF_PRESERVATION", "strategy": "merge_compatible"})

        issuers = {str(d.get("issuer_role", "")).lower() for d in directives}
        if "commander" in issuers and len(issuers) > 1:
            conflicts.append({"type": "ORDER_SUPERSESSION", "strategy": "commander_override"})

        return conflicts

    def resolve(
        self,
        directives: List[Dict[str, Any]],
        commander_override: bool = False,
    ) -> Dict[str, Any]:
        """Resolve conflicts with ROE-first policy unless commander overrides."""
        active = list(directives or [])
        conflicts = self.detect_conflicts(active)
        resolutions: List[Dict[str, Any]] = []

        for conflict in conflicts:
            ctype = str(conflict.get("type", ""))
            strategy = str(conflict.get("strategy", "escalate_to_human"))
            if ctype == "ROE_CONTRADICTION" and not commander_override:
                active = [
                    d
                    for d in active
                    if str(d.get("type", d.get("action", ""))).lower() != "engage"
                ]
                strategy = "priority_wins"
            elif ctype == "ORDER_SUPERSESSION":
                commander_only = [d for d in active if str(d.get("issuer_role", "")).lower() == "commander"]
                if commander_only:
                    active = commander_only
                strategy = "commander_override" if commander_only else strategy
            elif ctype == "RESOURCE_CONTENTION":
                active.sort(key=lambda d: float(d.get("utility", d.get("priority", 0.0))), reverse=True)
                used = set()
                filtered: List[Dict[str, Any]] = []
                for directive in active:
                    resource = directive.get("resource")
                    if resource is None:
                        filtered.append(directive)
                        continue
                    key = str(resource)
                    if key in used:
                        continue
                    used.add(key)
                    filtered.append(directive)
                active = filtered
                strategy = "cost_benefit"
            elif ctype == "MISSION_PRIORITY":
                top = max(int(d.get("priority", d.get("mission_priority", 3))) for d in active)
                active = [d for d in active if int(d.get("priority", d.get("mission_priority", 3))) == top]
                strategy = "priority_wins"
            elif ctype == "SELF_PRESERVATION":
                preserved = [d for d in active if bool(d.get("self_preservation"))]
                if preserved:
                    active = preserved
                strategy = "merge_compatible"

            resolutions.append(
                {
                    "type": ctype,
                    "strategy": strategy,
                    "remaining_directives": len(active),
                }
            )

        status = "resolved" if conflicts else "clean"
        result = {
            "status": status,
            "active_directives": active,
            "conflicts": conflicts,
            "resolutions": resolutions,
        }
        self.last_resolutions = list(resolutions)
        self.history.append(result)
        if len(self.history) > 5000:
            self.history = self.history[-5000:]
        return result

