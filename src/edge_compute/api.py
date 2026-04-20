"""
S3M Edge Compute API Routes
UNCLASSIFIED - FOUO

FastAPI router exposing both novel features via REST endpoints.
Mount into the main S3M API server with:
    app.include_router(edge_compute_router, prefix="/edge", tags=["Edge Compute"])
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.edge_compute.manager import EdgeComputeManager
from src.edge_compute.models import (
    EdgeNodeInfo,
    OperationType,
)
try:
    from src.edge_runtime.bootstrap import get_edge_runtime_status
except Exception:
    get_edge_runtime_status = lambda: {"status": "unavailable"}

logger = logging.getLogger("s3m.edge.api")

edge_compute_router = APIRouter()
_manager: Optional[EdgeComputeManager] = None


def get_manager() -> EdgeComputeManager:
    global _manager
    if _manager is None:
        _manager = EdgeComputeManager()
    return _manager


def set_manager(manager: Optional[EdgeComputeManager]) -> None:
    global _manager
    _manager = manager


class NodeRegistration(BaseModel):
    node_id: str = ""
    hostname: str = ""
    ip_address: str = ""
    port: int = 9090
    cpu_cores: int = 0
    memory_mb: int = 0
    gpu_available: bool = False


class SandboxDeployRequest(BaseModel):
    cpu_cores: int = Field(default=2, ge=1, le=64)
    memory_mb: int = Field(default=2048, ge=256, le=65536)
    gpu_passthrough: bool = False
    network_isolation: bool = True
    params: Dict[str, Any] = Field(default_factory=dict)


class ParamUpdateRequest(BaseModel):
    updates: Dict[str, Any]


class BootstrapRequest(BaseModel):
    parent_node_id: str
    target_memory_mb: int = Field(default=4096, ge=512)
    deploy_sandbox: bool = True


class FederatedGlobalInitRequest(BaseModel):
    input_dim: int = Field(default=8, ge=1, le=4096)
    output_dim: int = Field(default=4, ge=1, le=4096)


class FederatedRoundRequest(BaseModel):
    participating_nodes: List[str] = Field(default_factory=list)
    duration_seconds: float = Field(default=1.0, ge=0.0, le=86400.0)


class QuickSelfTrainRequest(BaseModel):
    input_dim: int = Field(default=8, ge=1, le=2048)
    output_dim: int = Field(default=4, ge=1, le=1024)
    labeled_x: List[List[float]] = Field(default_factory=list)
    labeled_y: List[int] = Field(default_factory=list)
    unlabeled_x: List[List[float]] = Field(default_factory=list)
    cycles: int = Field(default=5, ge=1, le=50)
    epochs_per_cycle: int = Field(default=3, ge=1, le=50)


class ContrastiveDataRequest(BaseModel):
    records: List[Dict[str, Any]] = Field(default_factory=list)


class ComputeExecuteRequest(BaseModel):
    operation: OperationType = OperationType.MATMUL
    left: List[List[float]] = Field(default_factory=list)
    right: List[List[float]] = Field(default_factory=list)


def _to_2d_float(payload: List[List[float]], name: str) -> np.ndarray:
    if not isinstance(payload, list) or not payload:
        raise HTTPException(status_code=400, detail=f"{name} must be a non-empty 2D array")
    try:
        arr = np.asarray(payload, dtype=np.float32)
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=400, detail=f"{name} invalid numeric payload: {exc}") from exc
    if arr.ndim != 2:
        raise HTTPException(status_code=400, detail=f"{name} must be a 2D array")
    return arr


def _to_1d_int(payload: List[int], expected: int, name: str) -> np.ndarray:
    if not isinstance(payload, list) or len(payload) != expected:
        raise HTTPException(status_code=400, detail=f"{name} must contain {expected} labels")
    try:
        arr = np.asarray(payload, dtype=np.int64)
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=400, detail=f"{name} invalid integer payload: {exc}") from exc
    if arr.ndim != 1:
        raise HTTPException(status_code=400, detail=f"{name} must be a 1D array")
    return arr


@edge_compute_router.get("/health")
async def edge_health() -> Dict[str, Any]:
    """
    Combined edge status for tactical operators.

    Returns legacy edge-compute health keys while exposing austere runtime status.
    """
    payload = get_manager().health_check()
    try:
        payload.update(get_edge_runtime_status())
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Edge runtime status unavailable during /edge/health: %s", exc)
    return payload


@edge_compute_router.post("/federated/nodes")
async def register_node(req: NodeRegistration) -> Dict[str, Any]:
    node = EdgeNodeInfo(**req.model_dump())
    get_manager().federated.register_node(node)
    return {"status": "registered", "node_id": node.node_id}


@edge_compute_router.delete("/federated/nodes/{node_id}")
async def deregister_node(node_id: str) -> Dict[str, Any]:
    get_manager().federated.deregister_node(node_id)
    return {"status": "deregistered", "node_id": node_id}


@edge_compute_router.get("/federated/nodes")
async def list_nodes() -> Dict[str, Any]:
    nodes = get_manager().federated.active_nodes()
    return {"nodes": [n.model_dump() for n in nodes]}


@edge_compute_router.get("/federated/status")
async def federated_status() -> Dict[str, Any]:
    return get_manager().federated.health_check()


@edge_compute_router.get("/federated/dp")
async def dp_status() -> Dict[str, Any]:
    return get_manager().federated.dp_status()


@edge_compute_router.get("/federated/rounds")
async def round_history() -> Dict[str, Any]:
    rounds = get_manager().federated.round_history()
    return {"rounds": [r.model_dump() for r in rounds]}


@edge_compute_router.post("/federated/global-model/init")
async def federated_global_model_init(req: FederatedGlobalInitRequest) -> Dict[str, Any]:
    # Tactical baseline model kept deterministic for disconnected field nodes.
    params = {
        "w": np.zeros((req.input_dim, req.output_dim), dtype=np.float32),
        "b": np.zeros((req.output_dim,), dtype=np.float32),
    }
    get_manager().federated.initialize_global_model(params)
    return {
        "status": "initialized",
        "shapes": {k: list(v.shape) for k, v in params.items()},
    }


@edge_compute_router.post("/federated/rounds")
async def federated_record_round(req: FederatedRoundRequest) -> Dict[str, Any]:
    round_info = get_manager().federated.record_round(
        participating_nodes=req.participating_nodes,
        duration_seconds=req.duration_seconds,
    )
    return round_info.model_dump()


@edge_compute_router.get("/self-training/status")
async def self_training_status() -> Dict[str, Any]:
    return get_manager().self_trainer.health_check()


@edge_compute_router.get("/self-training/history")
async def self_training_history() -> Dict[str, Any]:
    history = get_manager().self_trainer.history()
    return {"batches": [b.model_dump() for b in history]}


@edge_compute_router.post("/self-training/quick")
async def self_training_quick(req: QuickSelfTrainRequest) -> Dict[str, Any]:
    labeled_x = _to_2d_float(req.labeled_x, "labeled_x")
    unlabeled_x = _to_2d_float(req.unlabeled_x, "unlabeled_x")
    if labeled_x.shape[1] != req.input_dim or unlabeled_x.shape[1] != req.input_dim:
        raise HTTPException(status_code=400, detail="Input dimensions do not match input_dim")
    labeled_y = _to_1d_int(req.labeled_y, labeled_x.shape[0], "labeled_y")
    return get_manager().quick_self_train(
        input_dim=req.input_dim,
        output_dim=req.output_dim,
        labeled_x=labeled_x,
        labeled_y=labeled_y,
        unlabeled_x=unlabeled_x,
        cycles=req.cycles,
        epochs_per_cycle=req.epochs_per_cycle,
    )


@edge_compute_router.get("/replicas")
async def list_replicas() -> Dict[str, Any]:
    replicas = get_manager().replication.list_replicas()
    return {"replicas": [r.model_dump() for r in replicas]}


@edge_compute_router.get("/replicas/status")
async def replication_status() -> Dict[str, Any]:
    return get_manager().replication.health_check()


@edge_compute_router.delete("/replicas/{replica_id}")
async def stop_replica(replica_id: str) -> Dict[str, Any]:
    ok = get_manager().replication.stop_replica(replica_id)
    if not ok:
        raise HTTPException(404, f"Replica {replica_id} not found or already stopped")
    return {"status": "stopped", "replica_id": replica_id}


@edge_compute_router.post("/replicas/stop-all")
async def stop_all_replicas() -> Dict[str, Any]:
    get_manager().replication.stop_all()
    return {"status": "stopped_all"}


@edge_compute_router.get("/data-generation/status")
async def data_gen_status() -> Dict[str, Any]:
    return get_manager().data_gen.health_check()


@edge_compute_router.get("/data-generation/datasets")
async def list_generated_datasets() -> Dict[str, Any]:
    datasets = get_manager().data_gen.list_generated()
    return {"datasets": [d.model_dump() for d in datasets]}


@edge_compute_router.post("/data-generation/contrastive")
async def generate_contrastive_dataset(req: ContrastiveDataRequest) -> Dict[str, Any]:
    dataset = get_manager().data_gen.generate_contrastive_dataset(req.records)
    return dataset.model_dump()


@edge_compute_router.post("/data-generation/discover-relationships")
async def discover_relationships(min_count: int = 3, min_pmi: float = 1.0) -> Dict[str, Any]:
    new_edges = get_manager().data_gen.discover_relationships(min_count, min_pmi)
    return {"new_edges": new_edges}


@edge_compute_router.get("/knowledge-graph/stats")
async def kg_stats() -> Dict[str, Any]:
    return get_manager().data_gen.knowledge_graph.stats()


@edge_compute_router.get("/knowledge-graph/neighbors/{entity_name}")
async def kg_neighbors(entity_name: str, max_hops: int = 1) -> Dict[str, Any]:
    neighbors = get_manager().data_gen.knowledge_graph.query_neighbors(entity_name, max_hops)
    return {"entity": entity_name, "neighbors": neighbors}


@edge_compute_router.post("/sandbox/deploy")
async def deploy_sandbox(req: SandboxDeployRequest) -> Dict[str, Any]:
    state = get_manager().sandbox.deploy(
        cpu_cores=req.cpu_cores,
        memory_mb=req.memory_mb,
        gpu_passthrough=req.gpu_passthrough,
        network_isolation=req.network_isolation,
        params=req.params,
    )
    return state.model_dump()


@edge_compute_router.post("/sandbox/{sandbox_id}/params")
async def update_sandbox_params(sandbox_id: str, req: ParamUpdateRequest) -> Dict[str, Any]:
    try:
        updated = get_manager().sandbox.update_params(sandbox_id, req.updates)
        return {"sandbox_id": sandbox_id, "params": updated}
    except ValueError as exc:
        raise HTTPException(404, f"Sandbox {sandbox_id} not found") from exc


@edge_compute_router.get("/sandbox/{sandbox_id}/params")
async def get_sandbox_params(sandbox_id: str) -> Dict[str, Any]:
    try:
        return get_manager().sandbox.get_params(sandbox_id)
    except ValueError as exc:
        raise HTTPException(404, f"Sandbox {sandbox_id} not found") from exc


@edge_compute_router.post("/sandbox/{sandbox_id}/stop")
async def stop_sandbox(sandbox_id: str) -> Dict[str, Any]:
    ok = get_manager().sandbox.stop(sandbox_id)
    if not ok:
        raise HTTPException(404, f"Sandbox {sandbox_id} not found")
    return {"status": "stopped", "sandbox_id": sandbox_id}


@edge_compute_router.get("/sandbox/{sandbox_id}/logs")
async def sandbox_logs(sandbox_id: str, tail: int = 100) -> Dict[str, Any]:
    try:
        logs = get_manager().sandbox.get_logs(sandbox_id, tail)
    except ValueError as exc:
        raise HTTPException(404, f"Sandbox {sandbox_id} not found") from exc
    return {"sandbox_id": sandbox_id, "logs": logs}


@edge_compute_router.get("/sandbox/list")
async def list_sandboxes() -> Dict[str, Any]:
    sandboxes = get_manager().sandbox.list_sandboxes()
    return {"sandboxes": [s.model_dump() for s in sandboxes]}


@edge_compute_router.post("/sandbox/stop-all")
async def stop_all_sandboxes() -> Dict[str, Any]:
    get_manager().sandbox.stop_all()
    return {"status": "stopped_all"}


@edge_compute_router.post("/bootstrap")
async def bootstrap_node(req: BootstrapRequest) -> Dict[str, Any]:
    mgr = get_manager()
    global_params = mgr.federated.get_global_params()
    if not global_params:
        raise HTTPException(400, "No global model initialized. Initialize federated model first.")
    return mgr.bootstrap_edge_node(
        parent_params=global_params,
        parent_node_id=req.parent_node_id,
        target_memory_mb=req.target_memory_mb,
        deploy_sandbox=req.deploy_sandbox,
    )


@edge_compute_router.get("/compute/status")
async def compute_status() -> Dict[str, Any]:
    return get_manager().compute.health_check()


@edge_compute_router.get("/compute/capabilities")
async def compute_capabilities() -> Dict[str, Any]:
    return get_manager().compute.caps.to_dict()


@edge_compute_router.get("/compute/stats")
async def compute_device_stats() -> Dict[str, Any]:
    return get_manager().compute.device_stats()


@edge_compute_router.get("/compute/policy")
async def compute_policy_table() -> Dict[str, Any]:
    return get_manager().compute.scheduler.get_policy_table()


@edge_compute_router.post("/compute/execute")
async def compute_execute(req: ComputeExecuteRequest) -> Dict[str, Any]:
    left = _to_2d_float(req.left, "left")
    if req.operation == OperationType.MATMUL:
        right = _to_2d_float(req.right, "right")
        if left.shape[1] != right.shape[0]:
            raise HTTPException(status_code=400, detail="Matrix dimensions do not align for matmul")

        def _op() -> List[List[float]]:
            return (left @ right).tolist()

        result = get_manager().compute.execute(OperationType.MATMUL, _op)
    else:
        # Tactical fallback for non-matmul operations uses deterministic local reduction.
        def _op() -> float:
            return float(np.sum(left))

        result = get_manager().compute.execute(req.operation, _op)
    return result
