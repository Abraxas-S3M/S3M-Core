"""Mission planner adapter for multi-domain tactical planning.

This wrapper preserves backward-compatible import paths expected by
gap-closure integrations while delegating to existing S3M planners.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.apps.drone_ops.mission_planner import MissionPlanner as DroneMissionPlanner
from src.cortex.minimal_profile import plan_minimal_profile
from src.cortex.models import MinimalProfilePlan
from src.cortex.twin import NetworkTwin


class MultiDomainMissionPlanner:
    """Coordinate mission planning across available S3M planning modules."""

    def __init__(self, *, network_twin: NetworkTwin | None = None) -> None:
        self._drone_planner = DroneMissionPlanner()
        self._network_twin = network_twin or NetworkTwin()

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

    @property
    def network_twin(self) -> NetworkTwin:
        """Cortex connectivity twin shared with cyber quarantine planning."""
        return self._network_twin

    def plan_minimal_profile(self, node: str) -> MinimalProfilePlan:
        """Propose a mission-preserving PCCP narrow for a suspect twin node."""
        if not isinstance(node, str) or not node.strip():
            raise ValueError("node must be a non-empty string")
        return plan_minimal_profile(self._network_twin, node.strip())

