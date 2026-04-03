"""
FastAPI routes for S3M austere edge runtime controls.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.edge_runtime.bearer_broker import LinkMetrics, LinkState, LinkType, MessageClass
from src.edge_runtime.bootstrap import AustereEdgeRuntime
from src.edge_runtime.degradation_controller import DegradationController, OperatingMode


router = APIRouter(prefix="/edge", tags=["Edge Runtime"])

_runtime: Optional[AustereEdgeRuntime] = None


def get_runtime() -> AustereEdgeRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AustereEdgeRuntime()
    return _runtime


class BearerUpdate(BaseModel):
    link_type: str
    state: str
    latency_ms: float = 100.0
    bandwidth_kbps: float = 0.0
    packet_loss_pct: float = 0.0


class EnqueueRequest(BaseModel):
    message_class: str
    payload: dict
    priority: int = 5


class ModelPlanRequest(BaseModel):
    model_id: str
    requested_tokens: int = 512


@router.get("/status")
async def edge_status() -> dict:
    return get_runtime().status()


@router.get("/health")
async def edge_health() -> dict:
    runtime = get_runtime()
    return {"summary": runtime.health.summary_line(), "mode": runtime.controller.current_mode.value}


@router.get("/profile")
async def edge_profile() -> dict:
    return get_runtime().profile.to_dict()


@router.get("/mode")
async def edge_mode() -> dict:
    runtime = get_runtime()
    policy = runtime.controller.current_policy()
    return {
        "mode": runtime.controller.current_mode.value,
        "description": policy.description,
        "max_concurrent_models": policy.max_concurrent_models,
        "allow_gpu": policy.allow_gpu,
        "allow_large_transfers": policy.allow_large_transfers,
        "queue_outbound": policy.queue_outbound,
    }


@router.post("/mode/force")
async def force_mode(mode: str, reason: str = "operator_override") -> dict:
    try:
        target = OperatingMode(mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {mode}. Valid: full_edge, cpu_constrained, intermittent_link, offline_survival",
        ) from exc
    get_runtime().controller.force_mode(target, reason)
    return {"mode": target.value, "reason": reason}


@router.get("/transitions")
async def edge_transitions() -> list:
    return get_runtime().controller.get_transition_log()


@router.get("/bearers")
async def edge_bearers() -> list:
    return get_runtime().broker.bearer_status()


@router.put("/bearers")
async def update_bearer(update: BearerUpdate) -> dict:
    runtime = get_runtime()
    try:
        link_type = LinkType(update.link_type)
        link_state = LinkState(update.state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    metrics = LinkMetrics(
        link_type=link_type,
        state=link_state,
        latency_ms=update.latency_ms,
        bandwidth_kbps=update.bandwidth_kbps,
        packet_loss_pct=update.packet_loss_pct,
    )
    runtime.broker.register_bearer(link_type, metrics)
    runtime.controller.report_link_state(runtime.broker.any_bearer_up())
    return {"registered": link_type.value, "state": link_state.value}


@router.post("/route")
async def route_message(message_class: str, payload_size_kb: float = 0) -> dict:
    try:
        parsed = MessageClass(message_class)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid message_class: {message_class}") from exc
    return get_runtime().broker.route(parsed, payload_size_kb).to_dict()


@router.post("/plan")
async def plan_model(req: ModelPlanRequest) -> dict:
    return get_runtime().planner.plan(req.model_id, req.requested_tokens).to_dict()


@router.post("/queue")
async def enqueue_message(req: EnqueueRequest) -> dict:
    item_id = get_runtime().queue.enqueue(req.message_class, req.payload, req.priority)
    return {"item_id": item_id, "status": "queued"}


@router.get("/queue/stats")
async def queue_stats() -> dict:
    return get_runtime().queue.stats()


@router.post("/sync")
async def trigger_sync() -> dict:
    return get_runtime().reconciler.run_sync()


@router.get("/tiers")
async def service_tiers() -> dict:
    return DegradationController.service_tiers()
