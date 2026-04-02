"""
S3M Edge Compute Manager
UNCLASSIFIED - FOUO

Central coordinator for edge-compute subsystems used in tactical learning:
  - Self-growth for adaptive model capacity under mission drift
  - Governed replication for secure model propagation
  - Data value triage with self-cleaning hygiene controls
"""

from __future__ import annotations

import os
from typing import Any, Dict

from src.edge_compute.data_value_assessor import DataValueEngine
from src.edge_compute.governed_replication import GovernedReplicationEngine
from src.edge_compute.self_growth import SelfGrowthEngine


class EdgeComputeManager:
    """Facade over edge compute adaptive subsystems."""

    def __init__(self, max_replicas: int = 32):
        if max_replicas <= 0:
            raise ValueError("max_replicas must be > 0")

        self.self_growth = SelfGrowthEngine(max_layers=256, max_memory_mb=2048.0)
        self.governed_replication = GovernedReplicationEngine(
            secret_key=os.environ.get("S3M_REPLICATION_KEY", "CHANGE-IN-PRODUCTION"),
            max_fleet=max_replicas,
        )
        self.data_value = DataValueEngine(cleaning_mode="post_cycle")

    def health_check(self) -> Dict[str, Any]:
        return {
            "self_growth": self.self_growth.health_check(),
            "governed_replication": self.governed_replication.health_check(),
            "data_value": self.data_value.health_check(),
        }
