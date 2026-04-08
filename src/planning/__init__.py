"""Planning-layer mission abstractions for cross-domain orchestration."""

from __future__ import annotations

from typing import Any

__all__ = ["MultiDomainMissionPlanner", "TacticalRouteGraph"]


def __getattr__(name: str) -> Any:
    if name == "MultiDomainMissionPlanner":
        from src.planning.mission_planner import MultiDomainMissionPlanner

        return MultiDomainMissionPlanner
    if name == "TacticalRouteGraph":
        from src.planning.route_graph import TacticalRouteGraph

        return TacticalRouteGraph
    raise AttributeError(f"module 'src.planning' has no attribute '{name}'")
