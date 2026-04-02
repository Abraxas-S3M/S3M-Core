"""
S3M Layer 06 - Edge Compute Dashboard Provider
UNCLASSIFIED - FOUO

Read-only dashboard provider for edge compute orchestration.
Follows the existing safe-fallback pattern used by other providers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger("s3m.dashboard.edge_compute")


class EdgeComputeDashProvider:
    """Dashboard data provider for the edge computing subsystem."""

    def __init__(self) -> None:
        self._manager = None
        self._init_manager()

    def _init_manager(self) -> None:
        try:
            from src.edge_compute.api import _manager as global_mgr

            if global_mgr is not None:
                self._manager = global_mgr
            else:
                # Tactical-safe fallback keeps dashboard read-only when edge manager is not mounted.
                self._manager = None
        except Exception:
            logger.debug("Edge compute manager unavailable")
            self._manager = None

    def set_manager(self, manager) -> None:
        self._manager = manager

    def get_edge_network_overview(self) -> Dict[str, Any]:
        if self._manager is None:
            return self._empty_overview()
        try:
            fed = self._manager.federated
            nodes = fed.active_nodes()
            dp = fed.dp_status()
            rounds = fed.round_history()
            return {
                "registered_nodes": len(getattr(fed, "_nodes", {})),
                "active_nodes": len(nodes),
                "strategy": fed.strategy.value,
                "current_round": getattr(fed, "_round_counter", 0),
                "dp_epsilon_budget": dp.get("epsilon_budget", 0),
                "dp_epsilon_spent": round(float(dp.get("epsilon_spent", 0.0)), 4),
                "dp_budget_remaining_pct": round(
                    float(dp.get("epsilon_remaining", 0.0)) / float(dp.get("epsilon_budget", 1.0)) * 100.0,
                    1,
                )
                if float(dp.get("epsilon_budget", 0.0)) > 0.0
                else 0.0,
                "dp_exhausted": bool(dp.get("budget_exhausted", False)),
                "recent_rounds": [
                    {
                        "round_id": r.round_id,
                        "nodes": len(r.participating_nodes),
                        "duration_s": round(r.duration_seconds, 3),
                        "compressed": r.gradients_compressed,
                    }
                    for r in rounds[-10:]
                ],
                "node_roster": [
                    {
                        "node_id": n.node_id[:8],
                        "hostname": n.hostname,
                        "status": getattr(n.status, "value", n.status),
                        "cpu_cores": n.cpu_cores,
                        "memory_mb": n.memory_mb,
                        "gpu": n.gpu_available,
                    }
                    for n in nodes
                ],
            }
        except Exception as exc:
            logger.warning("Edge network overview failed: %s", exc)
            return self._empty_overview()

    def get_self_training_status(self) -> Dict[str, Any]:
        if self._manager is None:
            return {"strategy": "unavailable", "cycles": 0, "total_pseudo_labels": 0, "history": []}
        try:
            st = self._manager.self_trainer
            history = st.history()
            return {
                "strategy": st.strategy.value,
                "cycles": getattr(st, "_cycle", 0),
                "total_pseudo_labels": getattr(st, "_total_pseudo_labels", 0),
                "confidence_threshold": st.confidence_threshold,
                "teacher_ready": getattr(st, "_teacher", None) is not None,
                "student_ready": getattr(st, "_student", None) is not None,
                "history": [
                    {
                        "cycle": i + 1,
                        "sample_count": h.sample_count,
                        "avg_confidence": round(h.avg_confidence, 3),
                        "noise_applied": h.noise_applied,
                    }
                    for i, h in enumerate(history[-20:])
                ],
            }
        except Exception as exc:
            logger.warning("Self-training status failed: %s", exc)
            return {"strategy": "error", "cycles": 0, "total_pseudo_labels": 0, "history": []}

    def get_replica_fleet(self) -> Dict[str, Any]:
        if self._manager is None:
            return {"total": 0, "active": 0, "max": 0, "replicas": []}
        try:
            rep = self._manager.replication
            replicas = rep.list_replicas()
            active = sum(1 for r in replicas if getattr(r.status, "value", r.status) == "online")
            return {
                "total": len(replicas),
                "active": active,
                "max": rep.max_replicas,
                "runtime": rep.container_runtime,
                "runtime_available": getattr(rep, "_runtime_available", False),
                "replicas": [
                    {
                        "id": r.replica_id[:8],
                        "parent": r.parent_node_id[:8],
                        "status": getattr(r.status, "value", r.status),
                        "distillation_ratio": round(r.distillation_ratio, 2),
                        "container": (r.container_id or "")[:12],
                    }
                    for r in replicas
                ],
            }
        except Exception as exc:
            logger.warning("Replica fleet status failed: %s", exc)
            return {"total": 0, "active": 0, "max": 0, "replicas": []}

    def get_data_generation_status(self) -> Dict[str, Any]:
        if self._manager is None:
            return {"datasets": 0, "kg_entities": 0, "kg_edges": 0}
        try:
            dg = self._manager.data_gen
            datasets = dg.list_generated()
            kg = dg.knowledge_graph.stats()
            return {
                "datasets_generated": len(datasets),
                "total_records": sum(d.record_count for d in datasets),
                "total_size_bytes": sum(d.file_size_bytes for d in datasets),
                "kg_entities": kg.get("entities", 0),
                "kg_edges": kg.get("edges", 0),
                "replay_classes": len(dg.replay.fitted_classes),
                "recent_datasets": [
                    {
                        "id": d.dataset_id[:8],
                        "strategy": d.strategy.value,
                        "records": d.record_count,
                        "size_bytes": d.file_size_bytes,
                    }
                    for d in datasets[-10:]
                ],
            }
        except Exception as exc:
            logger.warning("Data gen status failed: %s", exc)
            return {"datasets": 0, "kg_entities": 0, "kg_edges": 0}

    def get_sandbox_fleet(self) -> Dict[str, Any]:
        if self._manager is None:
            return {"total": 0, "running": 0, "sandboxes": []}
        try:
            sb = self._manager.sandbox
            sandboxes = sb.list_sandboxes()
            running = sum(1 for s in sandboxes if s.running)
            return {
                "total": len(sandboxes),
                "running": running,
                "runtime": sb.runtime,
                "runtime_available": getattr(sb, "_runtime_available", False),
                "sandboxes": [
                    {
                        "id": s.sandbox_id[:8],
                        "running": s.running,
                        "training": s.parameters.get("training_enabled", False),
                        "inference": s.parameters.get("inference_enabled", False),
                        "temperature": s.parameters.get("temperature", 0.7),
                    }
                    for s in sandboxes
                ],
            }
        except Exception as exc:
            logger.warning("Sandbox fleet status failed: %s", exc)
            return {"total": 0, "running": 0, "sandboxes": []}

    def get_hetero_compute_status(self) -> Dict[str, Any]:
        if self._manager is None:
            return {"policy": "unavailable", "total_tasks": 0}
        try:
            hc = self._manager.compute
            stats = hc.device_stats()
            policy_table = hc.scheduler.get_policy_table()
            return {
                "policy": hc.policy.value,
                "gpu_available": hc.caps.gpu_available,
                "gpu_name": hc.caps.gpu_name,
                "cpu_cores": hc.caps.cpu_cores,
                "total_tasks": stats.get("total_tasks", 0),
                "cpu_tasks": stats.get("cpu", {}).get("tasks_completed", 0),
                "gpu_tasks": stats.get("gpu", {}).get("tasks_completed", 0),
                "cpu_avg_latency_ms": round(stats.get("cpu", {}).get("avg_latency_ms", 0.0), 2),
                "gpu_avg_latency_ms": round(stats.get("gpu", {}).get("avg_latency_ms", 0.0), 2),
                "policy_table": policy_table,
            }
        except Exception as exc:
            logger.warning("Hetero compute status failed: %s", exc)
            return {"policy": "error", "total_tasks": 0}

    def get_full_overview(self) -> Dict[str, Any]:
        return {
            "edge_network": self.get_edge_network_overview(),
            "self_training": self.get_self_training_status(),
            "replica_fleet": self.get_replica_fleet(),
            "data_generation": self.get_data_generation_status(),
            "sandboxes": self.get_sandbox_fleet(),
            "hetero_compute": self.get_hetero_compute_status(),
        }

    @staticmethod
    def _empty_overview() -> Dict[str, Any]:
        return {
            "registered_nodes": 0,
            "active_nodes": 0,
            "strategy": "unavailable",
            "current_round": 0,
            "dp_epsilon_budget": 0,
            "dp_epsilon_spent": 0,
            "dp_budget_remaining_pct": 0,
            "dp_exhausted": False,
            "recent_rounds": [],
            "node_roster": [],
        }
