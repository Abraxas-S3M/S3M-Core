"""Mission planner adapter for multi-domain tactical planning.

This wrapper preserves backward-compatible import paths expected by
gap-closure integrations while delegating to existing S3M planners.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.apps.drone_ops.mission_planner import MissionPlanner as DroneMissionPlanner


class MultiDomainMissionPlanner:
    """Coordinate mission planning across available S3M planning modules."""

    def __init__(self) -> None:
        self._drone_planner = DroneMissionPlanner()

    def plan(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Create a mission plan from structured request payload."""
        if not isinstance(request, dict):
            raise ValueError("request must be a dictionary")
        return self._drone_planner.plan_mission(request)

    def plan_from_text(self, text: str, language: str = "en") -> Dict[str, Any]:
        """Create a mission plan from natural language tasking text."""
        return self._drone_planner.plan_from_nl(text, language=language)

    def list_missions(self) -> List[Dict[str, Any]]:
        """Return all currently tracked mission plans."""
        return self._drone_planner.get_missions()

    def health_check(self) -> Dict[str, Any]:
        """Return planner health without loading heavyweight assets."""
        return {
            "status": "operational",
            "component": "multi_domain_mission_planner",
            "missions_tracked": len(self._drone_planner.get_missions()),
            "offline_mode": True,
        }

