"""FastAPI routes for the Quad-Engine Orchestration Demo Layer.

Tactical context:
    These endpoints expose the quad-engine orchestration demo to S3M-GUI. The
    GUI never touches model files, R2, or vault storage directly; it only ever
    receives advisory recommendations / briefs / summaries through this API.

Safety doctrine:
    * No endpoint starts training, the trainer, the sync daemon, RunPod, or
      calls Grok/xAI. No credentials are exposed.
    * Every produced result is ``human_review_required`` and never authorizes
      autonomous or kinetic action.
    * If local models are absent or disabled, endpoints return deterministic
      demo output instead of errors -- the demo must never go blank.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.quad_engine.audit_log import get_audit_log
from src.quad_engine.local_llm import get_local_llm
from src.quad_engine.model_registry import get_registry, local_llm_enabled
from src.integrations.lechonk.flags import lechonk_enabled
from src.integrations.lechonk.status import compute_planning_readiness
from src.quad_engine.models import (
    BackendReadiness,
    OperationalPacket,
    OrchestratorStatus,
    QuadEngineResult,
)
from src.quad_engine.orchestrator import get_orchestrator

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quad-engine", tags=["Quad-Engine Orchestration"])


class CopBriefRequest(BaseModel):
    """Optional body for the deterministic COP commander brief demo."""

    track: str = Field(default="saudi_mod", max_length=64)


@router.get("/status", response_model=OrchestratorStatus)
async def quad_engine_status() -> OrchestratorStatus:
    """Report orchestration-layer status and safety posture."""
    registry = get_registry()
    runner = get_local_llm()
    planning = compute_planning_readiness()
    planning_view = BackendReadiness(
        phase=planning.phase.value,
        backing_engine_id=planning.backing_engine_id,
        precision=planning.precision,
        runtime=planning.runtime,
        device=planning.device,
        fallback_reason=planning.fallback_reason,
        profile=planning.profile,
    )
    return OrchestratorStatus(
        status="operational",
        mode="demo",
        local_llm_enabled=local_llm_enabled(),
        local_llm_available=runner.runner_available(),
        models_dir=registry.models_dir,
        engines=registry.engine_status_map(),
        planning_backend=planning_view,
        lechonk_feature_flag=lechonk_enabled(),
        autonomous_action_enabled=False,
        human_review_required=True,
        external_apis_called=False,
    )


@router.get("/engines")
async def quad_engine_engines() -> Dict[str, Any]:
    """List the four reasoning engines and their current status."""
    registry = get_registry()
    records = registry.to_records()
    return {
        "engines": [record.model_dump() for record in records],
        "total": len(records),
    }


@router.post("/packet", response_model=QuadEngineResult)
async def quad_engine_packet(packet: OperationalPacket) -> QuadEngineResult:
    """Classify, route, and orchestrate a single operational packet.

    Returns structured AI output even when no local models are present.
    """
    orchestrator = get_orchestrator()
    return orchestrator.process_packet(packet)


@router.get("/results/{result_id}", response_model=QuadEngineResult)
async def quad_engine_result(result_id: str) -> QuadEngineResult:
    """Retrieve a previously produced orchestration result by id."""
    orchestrator = get_orchestrator()
    result = orchestrator.get_result(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Result not found: {result_id}")
    return result


@router.get("/audit")
async def quad_engine_audit(limit: int = 50, action: Optional[str] = None) -> Dict[str, Any]:
    """Return recent orchestration audit entries."""
    audit = get_audit_log()
    logs = audit.recent(limit=limit, action=action)
    return {"logs": logs, "total": audit.count()}


@router.post("/demo/cop-brief", response_model=QuadEngineResult)
async def quad_engine_cop_brief(request: Optional[CopBriefRequest] = None) -> QuadEngineResult:
    """Generate a deterministic commander brief from the Saudi MOD COP demo.

    Pulls the COP state internally (no external calls). If the COP layer is
    unavailable for any reason, falls back to an empty snapshot so the brief is
    always produced -- the demo must never go blank.
    """
    track = (request.track if request else "saudi_mod") or "saudi_mod"
    cop_state: Dict[str, Any] = {"track": track}

    try:
        from src.cop.cop_service import CopService

        service = CopService()
        state = await service.get_state(track)
        cop_state = state.model_dump() if hasattr(state, "model_dump") else dict(state)
    except Exception as exc:  # pragma: no cover - defensive demo resilience
        LOGGER.warning("COP state unavailable for brief (%s); using empty snapshot: %s", track, exc)
        cop_state = {"track": track, "tactical_tracks": [], "alerts": [], "decisions": []}

    orchestrator = get_orchestrator()
    return orchestrator.build_cop_brief(cop_state)
