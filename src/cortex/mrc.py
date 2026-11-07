"""Minimum Response Cost (MRC) — mission-weighted disruption costing for Cortex."""

from __future__ import annotations

from typing import Dict, List, Optional

from src.cortex.config import load_cortex_config, mission_weight
from src.cortex.models import NetworkEdge
from src.cortex.twin import NetworkTwin


class MissionResponseCost:
    """Score edges for containment; active-mission edges cost more to disrupt."""

    def __init__(self, config: Optional[Dict] = None) -> None:
        self._config = config or load_cortex_config()

    def weighted_disruption_cost(self, edge: NetworkEdge, twin: NetworkTwin) -> float:
        base = float(edge.disruption_cost or self._config.get("default_disruption_cost", 1.0))
        priority = twin.highest_active_priority_on_edge(edge.edge_id)
        if priority <= 0:
            return base
        return base * mission_weight(priority, self._config)

    def select_disruption_target(
        self, candidates: List[NetworkEdge], twin: NetworkTwin
    ) -> NetworkEdge:
        """Pick the lowest weighted-cost edge (avoids high-cost mission edges)."""
        if not candidates:
            raise ValueError("no disruption candidates")
        scored = [(self.weighted_disruption_cost(edge, twin), edge) for edge in candidates]
        scored.sort(key=lambda pair: pair[0])
        return scored[0][1]
