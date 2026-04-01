"""FastAPI routes for autonomous kill-chain infrastructure.

Military context:
Routes expose controlled engagement workflows with mandatory veto controls and
full audit transparency for tactical command authorities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from services.killchain.f2t2ea_pipeline import F2T2EAPipeline
from services.killchain.models import EngagementAuthority


router = APIRouter()
_PIPELINE = F2T2EAPipeline()


@router.post("/killchain/detect")
async def detect(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run find+fix+track stages for tactical target detection."""
    found = _PIPELINE.find(payload)
    fixed = [_PIPELINE.fix(t) for t in found]
    tracked = [_PIPELINE.track(t) for t in fixed]
    return {"targets": [t.__dict__ for t in tracked]}


@router.post("/killchain/assess-target")
async def assess_target(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run target assessment phase and produce engagement request."""
    chain = _PIPELINE.execute_chain(payload)
    if not chain.get("target"):
        raise HTTPException(status_code=404, detail="no target available")
    return {"engagement_request": chain["target"]}


@router.post("/killchain/engage")
async def engage(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Execute full chain or engage an existing pending request."""
    request_id = payload.get("request_id")
    if request_id:
        req = _PIPELINE._requests.get(str(request_id))
        if not req:
            raise HTTPException(status_code=404, detail="request not found")
        result = _PIPELINE.engage(req)
        if req.request_id in _PIPELINE._bda:
            bda = _PIPELINE._bda[req.request_id]
        else:
            bda = _PIPELINE.assess(req)
        return {"engage": result, "bda": bda.__dict__}

    authority_raw = payload.get("authority_level")
    authority = None
    if authority_raw is not None:
        authority = EngagementAuthority(int(authority_raw))
    return _PIPELINE.execute_chain(payload, authority=authority)


@router.post("/killchain/engage/{id}/approve")
async def approve_engagement(id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Human approve pending engagement request."""
    req = _PIPELINE._requests.get(id)
    if not req:
        raise HTTPException(status_code=404, detail="request not found")
    req.status = "approved"
    req.human_decision = "approved"
    req.human_decision_by = str(payload.get("commander_id", "commander"))
    req.human_decision_at = datetime.now(timezone.utc)
    return {"status": "approved", "request_id": id}


@router.post("/killchain/engage/{id}/veto")
async def veto_engagement(id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Human veto endpoint that remains always available."""
    req = _PIPELINE._requests.get(id)
    if not req:
        raise HTTPException(status_code=404, detail="request not found")
    req.status = "vetoed"
    req.human_decision = "vetoed"
    req.human_decision_by = str(payload.get("commander_id", "commander"))
    req.human_decision_at = datetime.now(timezone.utc)
    return {"status": "vetoed", "request_id": id}


@router.get("/killchain/engage/{id}/bda")
async def bda(id: str) -> Dict[str, Any]:
    """Return battle damage assessment for engagement request."""
    record = _PIPELINE._bda.get(id)
    if not record:
        raise HTTPException(status_code=404, detail="bda not found")
    return record.__dict__


@router.get("/killchain/pending")
async def pending() -> Dict[str, Any]:
    """List pending human approvals for current authority mode."""
    return {"pending": [r.__dict__ for r in _PIPELINE.get_pending_approvals()]}


@router.get("/killchain/log")
async def log(limit: int = 50) -> Dict[str, Any]:
    """Return kill-chain audit log entries with XAI context."""
    entries = _PIPELINE.get_engagement_log(limit=limit)
    return {"entries": [e.__dict__ for e in entries]}


@router.get("/killchain/interlocks")
async def interlocks() -> Dict[str, Any]:
    """Return hard safety interlock status."""
    return {"interlocks": _PIPELINE.interlocks.get_interlock_status()}


@router.get("/killchain/authority")
async def authority_get() -> Dict[str, Any]:
    """Get current engagement authority level."""
    return {"authority_level": _PIPELINE.authority_level.value}


@router.post("/killchain/authority")
async def authority_set(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Set engagement authority level with commander approval evidence."""
    if not payload.get("commander_approval"):
        raise HTTPException(status_code=400, detail="commander_approval required")
    level = EngagementAuthority(int(payload.get("authority_level", 1)))
    _PIPELINE.authority_level = level
    return {"authority_level": level.value, "status": "updated"}


@router.get("/killchain/status")
async def status() -> Dict[str, Any]:
    """Return kill-chain subsystem operational status."""
    return {
        "status": "operational",
        "authority_level": _PIPELINE.authority_level.value,
        "pending_approvals": len(_PIPELINE.get_pending_approvals()),
        "audit_entries": len(_PIPELINE.get_engagement_log(limit=10000)),
    }
