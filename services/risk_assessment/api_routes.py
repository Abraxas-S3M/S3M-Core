"""FastAPI routes for risk assessment services.

Military context:
Routes provide mission and engagement risk gates so commanders can enforce
risk acceptance policy before autonomous operations proceed.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from services.risk_assessment.cost_estimator import CostEstimator
from services.risk_assessment.risk_engine import RiskEngine


router = APIRouter()
_ENGINE = RiskEngine()
_COST = CostEstimator()


@router.post("/risk/assess/mission")
async def assess_mission(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Assess mission risk from mission, assets, and personnel payload."""
    assessment = _ENGINE.assess_mission(
        mission=dict(payload.get("mission", {})),
        assets=list(payload.get("assets", [])),
        personnel=list(payload.get("personnel", [])),
    )
    return assessment.to_dict()


@router.post("/risk/assess/engagement")
async def assess_engagement(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Assess risk for a specific engagement request."""
    assessment = _ENGINE.assess_engagement(dict(payload.get("engagement_request", payload)))
    return assessment.to_dict()


@router.post("/risk/assess/patrol")
async def assess_patrol(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Assess patrol route risk from route geometry and assets."""
    assessment = _ENGINE.assess_patrol(route=list(payload.get("route", [])), assets=list(payload.get("assets", [])))
    return assessment.to_dict()


@router.post("/risk/assess/{id}/accept")
async def accept_risk(id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Commander risk acceptance endpoint for RED/BLACK assessments."""
    commander_id = payload.get("commander_id")
    if not commander_id:
        raise HTTPException(status_code=400, detail="commander_id required")
    assessment = _ENGINE._assessments.get(id)
    if not assessment:
        raise HTTPException(status_code=404, detail="assessment not found")
    assessment.approved_by = commander_id
    return {"status": "accepted", "assessment_id": id, "approved_by": commander_id}


@router.get("/risk/dashboard")
async def dashboard() -> Dict[str, Any]:
    """Return force-wide risk dashboard summary."""
    return _ENGINE.get_force_risk_dashboard()


@router.get("/risk/history/{entity_id}")
async def history(entity_id: str, days: int = 90) -> Dict[str, Any]:
    """Return risk history profile for selected entity."""
    profile = _ENGINE.get_risk_history(entity_id, days=days)
    return {
        "entity_id": profile.entity_id,
        "entity_type": profile.entity_type,
        "risk_history": profile.risk_history,
        "cumulative_risk_exposure": profile.cumulative_risk_exposure,
        "incidents": profile.incidents,
    }


@router.get("/risk/cost-table")
async def cost_table() -> Dict[str, Any]:
    """Return cost reference table used for expected-loss estimation."""
    return {"asset_costs": _COST.cost_table}


@router.get("/risk/status")
async def status() -> Dict[str, Any]:
    """Return risk subsystem health metrics."""
    return {
        "status": "operational",
        "assessments_cached": len(_ENGINE._assessments),
        "history_profiles": len(_ENGINE._history),
        "bayesian_initialized": _ENGINE.bayes.initialized,
    }
