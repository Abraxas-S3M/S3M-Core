"""Portal routes exposing integrated gap-closure modules."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from src.command import MissionCommandEngine
from src.force_awareness import ForceAwarenessManager
from src.logistics import SupplyChainTwin
from src.planning import MultiDomainMissionPlanner

router = APIRouter()

_command_engine = MissionCommandEngine()
_force_awareness = ForceAwarenessManager()
_logistics_twin = SupplyChainTwin()
_mission_planner = MultiDomainMissionPlanner()


def _as_http_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/portal/health")
async def portal_health() -> Dict[str, Any]:
    """Integrated portal health for tactical C2 dashboards."""
    return {
        "status": "operational",
        "components": {
            "command_engine": _command_engine.health_check(),
            "force_awareness": _force_awareness.health_check(),
            "logistics_twin": _logistics_twin.health_check(),
            "mission_planner": _mission_planner.health_check(),
        },
    }


@router.post("/portal/command/issue")
async def portal_issue_command(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Issue command through the mission command engine."""
    try:
        return _command_engine.issue_command(payload)
    except Exception as exc:
        raise _as_http_error(exc) from exc


@router.post("/portal/force/ingest")
async def portal_ingest_force_tracks(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Ingest force tracks for unified force awareness."""
    try:
        tracks = payload.get("tracks", [])
        if not isinstance(tracks, list):
            raise ValueError("tracks must be a list")
        return _force_awareness.ingest_tracks(tracks)
    except Exception as exc:
        raise _as_http_error(exc) from exc


@router.post("/portal/logistics/predict")
async def portal_predict_logistics(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run logistics twin sustainment risk prediction."""
    try:
        records = payload.get("records", [])
        if not isinstance(records, list):
            raise ValueError("records must be a list")
        return _logistics_twin.predict_disruptions(records)
    except Exception as exc:
        raise _as_http_error(exc) from exc


@router.post("/portal/planning/mission")
async def portal_plan_mission(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a mission plan using multi-domain planner."""
    try:
        return _mission_planner.plan(payload)
    except Exception as exc:
        raise _as_http_error(exc) from exc
