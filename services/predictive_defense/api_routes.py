"""FastAPI routes for predictive defense engine.

Military context:
These routes provide command-post access to tactical prediction products,
swarm indicators, and posture-driven defensive recommendations.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from services.predictive_defense.predictive_defense_manager import PredictiveDefenseManager

router = APIRouter(prefix="/predictive-defense", tags=["predictive_defense"])

_manager = PredictiveDefenseManager()


@router.get("/predictions")
async def get_predictions() -> Dict[str, Any]:
    preds = _manager.get_predictions()
    return {"predictions": [p.to_dict() for p in preds], "count": len(preds)}


@router.get("/swarm")
async def get_swarm() -> Dict[str, Any]:
    swarm = _manager.get_swarm_analysis()
    return {"swarm": swarm.to_dict() if swarm else None}


@router.get("/commands")
async def get_commands() -> Dict[str, Any]:
    cmds = _manager.get_commands()
    return {"commands": [c.to_dict() for c in cmds], "count": len(cmds)}


@router.get("/alerts")
async def get_alerts(limit: int = Query(default=20, ge=1, le=200)) -> Dict[str, Any]:
    alerts = _manager.get_alerts(limit)
    return {"alerts": [a.to_dict() for a in alerts]}


@router.get("/posture")
async def get_posture() -> Dict[str, Any]:
    alerts = _manager.get_alerts(1)
    if alerts:
        return {"posture": alerts[-1].posture.value, "severity": alerts[-1].severity}
    return {"posture": "normal", "severity": "low"}


@router.get("/stats")
async def get_stats() -> Dict[str, Any]:
    return _manager.get_stats()


@router.post("/genome-context")
async def set_genome_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    track_id = str(payload.get("track_id", "")).strip()
    if not track_id:
        raise HTTPException(status_code=400, detail="track_id required")

    context_raw = payload.get("context", {})
    if not isinstance(context_raw, dict):
        raise HTTPException(status_code=400, detail="context must be an object")

    try:
        _manager.set_genome_context(track_id, dict(context_raw))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"track_id": track_id, "status": "context_set"}

