"""Self-replication engine for tactical edge node scaling."""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional

import numpy as np

from src.edge_compute.models import ReplicaSpec, ReplicaStatus

logger = logging.getLogger("s3m.edge.replication")


class ReplicationEngine:
    """Create and manage lightweight replica records for edge deployment."""

    def __init__(self, max_replicas: int = 8, container_runtime: str = "docker") -> None:
        self.max_replicas = max(1, int(max_replicas))
        self.container_runtime = container_runtime
        self._replicas: Dict[str, ReplicaSpec] = {}
        self._runtime_available = False

    def create_replica(
        self,
        parent_node_id: str,
        parent_params: Dict[str, np.ndarray],
        target_memory_mb: int = 4096,
    ) -> ReplicaSpec:
        if not isinstance(parent_node_id, str) or not parent_node_id.strip():
            raise ValueError("parent_node_id must be a non-empty string")
        if len(self._replicas) >= self.max_replicas:
            raise ValueError("max replicas reached")
        if not isinstance(parent_params, dict) or not parent_params:
            raise ValueError("parent_params must be a non-empty parameter dictionary")

        # Tactical sizing rule: lower memory nodes receive stronger distillation.
        memory = max(256, int(target_memory_mb))
        ratio = 0.35 if memory <= 2048 else 0.5 if memory <= 4096 else 0.7
        replica_id = f"rep-{uuid.uuid4().hex[:12]}"
        replica = ReplicaSpec(
            replica_id=replica_id,
            parent_node_id=parent_node_id,
            status=ReplicaStatus.ONLINE,
            target_memory_mb=memory,
            distillation_ratio=ratio,
            container_id=f"ctr-{uuid.uuid4().hex[:12]}",
        )
        self._replicas[replica_id] = replica
        logger.info("Created replica %s from parent %s", replica_id, parent_node_id)
        return replica

    def list_replicas(self) -> List[ReplicaSpec]:
        return list(self._replicas.values())

    def stop_replica(self, replica_id: str) -> bool:
        replica = self._replicas.get(replica_id)
        if replica is None or replica.status == ReplicaStatus.STOPPED:
            return False
        replica.status = ReplicaStatus.STOPPED
        return True

    def stop_all(self) -> None:
        for replica in self._replicas.values():
            replica.status = ReplicaStatus.STOPPED

    def health_check(self) -> Dict[str, object]:
        replicas = self.list_replicas()
        active = sum(1 for r in replicas if r.status == ReplicaStatus.ONLINE)
        return {
            "status": "operational",
            "max_replicas": self.max_replicas,
            "total_replicas": len(replicas),
            "active_replicas": active,
            "runtime": self.container_runtime,
            "runtime_available": self._runtime_available,
        }
