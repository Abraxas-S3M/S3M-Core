"""FastAPI routes for S3M Phase 9 dashboard and live operator interface."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query, WebSocket, WebSocketDisconnect

from src.api.dashboard_models import (
    AgentRosterResponse,
    AgentRosterItem,
    AlertCountResponse,
    AlertItemResponse,
    AlertListResponse,
    COPDataResponse,
    DashboardOverviewResponse,
    DecisionFeedResponse,
    DecisionFeedItem,
    DecisionExplanationResponse,
    EdgeModelListResponse,
    EdgeModelItem,
    EngineStatusResponse,
    EngineStatusItem,
    JetsonStatsResponse,
    LLMMetricsResponse,
    MissionListResponse,
    MissionItem,
    NLCommandRequest,
    NLCommandResponse,
    ReviewQueueResponse,
    ReviewQueueItem,
    SystemHealthResponse,
    ThreatFeedResponse,
    ThreatFeedItem,
    ThreatHeatmapResponse,
    ThreatHeatmapItem,
    ThreatStatsResponse,
)
from src.dashboard.aggregator import DashboardAggregator
from src.dashboard.websocket_manager import WebSocketManager

dashboard_router = APIRouter()
_dashboard = DashboardAggregator()
_ws_manager = WebSocketManager()
_audit_log: List[Dict[str, Any]] = []


def _validate_collection(model_cls: Any, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    validated: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            validated.append(model_cls.model_validate(item).model_dump())
        except Exception:
            continue
    return validated


def _audit(action: str, details: Dict[str, Any]) -> None:
    _audit_log.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "details": details,
        }
    )
    if len(_audit_log) > 2000:
        del _audit_log[:-2000]


def _safe_level(level: Optional[str]) -> Optional[str]:
    if level is None:
        return None
    normalized = str(level).strip().upper()
    if normalized not in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}:
        raise HTTPException(status_code=400, detail="Invalid level")
    return normalized


@dashboard_router.get("/dashboard/status")
async def dashboard_status() -> Dict[str, Any]:
    payload = _dashboard.health_check()
    payload["ws_connections"] = _ws_manager.get_connection_count()
    payload["audit_entries"] = len(_audit_log)
    return payload


@dashboard_router.get("/dashboard/overview", response_model=DashboardOverviewResponse)
async def dashboard_overview() -> DashboardOverviewResponse:
    _audit("dashboard_overview", {})
    data = _dashboard.get_overview()
    return DashboardOverviewResponse.model_validate(data)


@dashboard_router.get("/dashboard/alerts", response_model=AlertListResponse)
async def dashboard_alerts(
    level: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> AlertListResponse:
    normalized_level = _safe_level(level)
    alerts = _dashboard.get_alerts(level=normalized_level, limit=limit)
    _audit("dashboard_alerts", {"level": normalized_level, "limit": limit, "count": len(alerts)})
    validated = _validate_collection(AlertItemResponse, alerts)
    return AlertListResponse(alerts=validated, total=len(validated))


@dashboard_router.get("/dashboard/alerts/count", response_model=AlertCountResponse)
async def dashboard_alert_counts() -> AlertCountResponse:
    counts = _dashboard.alert_manager.get_alert_counts()
    return AlertCountResponse(**counts)


@dashboard_router.get("/dashboard/cop", response_model=COPDataResponse)
async def dashboard_cop() -> COPDataResponse:
    return COPDataResponse.model_validate(_dashboard.cop_provider.get_cop_data())


@dashboard_router.get("/dashboard/cop/agents")
async def dashboard_cop_agents() -> Dict[str, Any]:
    agents = _dashboard.cop_provider.get_agents()
    return {"agents": agents, "total": len(agents)}


@dashboard_router.get("/dashboard/cop/threats")
async def dashboard_cop_threats() -> Dict[str, Any]:
    threats = _dashboard.cop_provider.get_threats()
    return {"threats": threats, "total": len(threats)}


@dashboard_router.get("/dashboard/cop/tracks")
async def dashboard_cop_tracks() -> Dict[str, Any]:
    tracks = _dashboard.cop_provider.get_tracks()
    return {"tracks": tracks, "total": len(tracks)}


@dashboard_router.get("/dashboard/cop/paths")
async def dashboard_cop_paths() -> Dict[str, Any]:
    paths = _dashboard.cop_provider.get_paths()
    return {"paths": paths, "total": len(paths)}


@dashboard_router.get("/dashboard/llm/status", response_model=EngineStatusResponse)
async def dashboard_llm_status() -> EngineStatusResponse:
    engines = _dashboard.llm_provider.get_engine_status()
    validated = _validate_collection(EngineStatusItem, engines)
    return EngineStatusResponse(engines=validated, total=len(validated))


@dashboard_router.get("/dashboard/llm/metrics", response_model=LLMMetricsResponse)
async def dashboard_llm_metrics() -> LLMMetricsResponse:
    return LLMMetricsResponse.model_validate(_dashboard.llm_provider.get_metrics())


@dashboard_router.get("/dashboard/llm/audit")
async def dashboard_llm_audit(limit: int = Query(default=20, ge=1, le=200)) -> Dict[str, Any]:
    entries = _dashboard.llm_provider.get_audit_log(limit=limit)
    return {"entries": entries, "total": len(entries)}


@dashboard_router.get("/dashboard/threats/feed", response_model=ThreatFeedResponse)
async def dashboard_threat_feed(
    level: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> ThreatFeedResponse:
    normalized_level = _safe_level(level)
    feed = _dashboard.threat_provider.get_threat_feed(level=normalized_level, limit=limit)
    validated = _validate_collection(ThreatFeedItem, feed)
    return ThreatFeedResponse(events=validated, total=len(validated))


@dashboard_router.get("/dashboard/threats/stats", response_model=ThreatStatsResponse)
async def dashboard_threat_stats() -> ThreatStatsResponse:
    return ThreatStatsResponse.model_validate(_dashboard.threat_provider.get_threat_stats())


@dashboard_router.get("/dashboard/threats/heatmap", response_model=ThreatHeatmapResponse)
async def dashboard_threat_heatmap() -> ThreatHeatmapResponse:
    heatmap = _dashboard.threat_provider.get_threat_heatmap()
    validated = _validate_collection(ThreatHeatmapItem, heatmap)
    return ThreatHeatmapResponse(items=validated, total=len(validated))


@dashboard_router.get("/dashboard/autonomy/agents", response_model=AgentRosterResponse)
async def dashboard_autonomy_agents() -> AgentRosterResponse:
    agents = _dashboard.autonomy_provider.get_agent_roster()
    validated = _validate_collection(AgentRosterItem, agents)
    return AgentRosterResponse(agents=validated, total=len(validated))


@dashboard_router.get("/dashboard/autonomy/missions", response_model=MissionListResponse)
async def dashboard_autonomy_missions() -> MissionListResponse:
    missions = _dashboard.autonomy_provider.get_missions()
    validated = _validate_collection(MissionItem, missions)
    return MissionListResponse(missions=validated, total=len(validated))


@dashboard_router.get("/dashboard/autonomy/decisions/feed", response_model=DecisionFeedResponse)
async def dashboard_autonomy_decision_feed(
    limit: int = Query(default=20, ge=1, le=200),
) -> DecisionFeedResponse:
    decisions = _dashboard.autonomy_provider.get_decision_feed(limit=limit)
    validated = _validate_collection(DecisionFeedItem, decisions)
    return DecisionFeedResponse(decisions=validated, total=len(validated))


@dashboard_router.get("/dashboard/autonomy/decisions/review", response_model=ReviewQueueResponse)
async def dashboard_autonomy_review_queue() -> ReviewQueueResponse:
    queue = _dashboard.autonomy_provider.get_review_queue()
    validated = _validate_collection(ReviewQueueItem, queue)
    return ReviewQueueResponse(items=validated, total=len(validated))


@dashboard_router.get(
    "/dashboard/autonomy/decisions/{decision_id}/explanation",
    response_model=DecisionExplanationResponse,
)
async def dashboard_autonomy_decision_explanation(decision_id: str) -> DecisionExplanationResponse:
    payload = _dashboard.autonomy_provider.get_decision_explanation(decision_id)
    return DecisionExplanationResponse.model_validate(payload)


@dashboard_router.post("/dashboard/autonomy/command", response_model=NLCommandResponse)
async def dashboard_autonomy_command(req: NLCommandRequest) -> NLCommandResponse:
    result = _dashboard.autonomy_provider.send_nl_command(text=req.text, language=req.language)
    _audit("autonomy_nl_command", {"language": req.language, "text_len": len(req.text)})
    if result.get("status") != "ok":
        raise HTTPException(status_code=400, detail=str(result.get("detail", "command failed")))
    return NLCommandResponse(status="ok", parsed_command=result.get("parsed_command", {}))


@dashboard_router.post("/autonomy/decisions/{decision_id}/approve")
async def approve_decision(decision_id: str) -> Dict[str, Any]:
    result = _dashboard.autonomy_provider.apply_review_decision(
        decision_id=decision_id,
        approved=True,
    )
    if result.get("status") != "ok":
        raise HTTPException(status_code=404, detail=str(result.get("detail", "Decision not found")))
    _audit("autonomy_decision_approve", {"decision_id": decision_id})
    return result


@dashboard_router.post("/autonomy/decisions/{decision_id}/reject")
async def reject_decision(decision_id: str, payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    reason = ""
    if isinstance(payload, dict):
        reason = str(payload.get("reason", "")).strip()
    result = _dashboard.autonomy_provider.apply_review_decision(
        decision_id=decision_id,
        approved=False,
        reason=reason,
    )
    if result.get("status") != "ok":
        raise HTTPException(status_code=404, detail=str(result.get("detail", "Decision not found")))
    _audit("autonomy_decision_reject", {"decision_id": decision_id, "reason": reason})
    return result


@dashboard_router.get("/dashboard/system/health", response_model=SystemHealthResponse)
async def dashboard_system_health() -> SystemHealthResponse:
    return SystemHealthResponse.model_validate(_dashboard.system_provider.get_system_health())


@dashboard_router.get("/dashboard/system/jetson", response_model=JetsonStatsResponse)
async def dashboard_system_jetson() -> JetsonStatsResponse:
    return JetsonStatsResponse.model_validate(_dashboard.system_provider.get_jetson_stats())


@dashboard_router.get("/dashboard/system/edge-models", response_model=EdgeModelListResponse)
async def dashboard_system_edge_models() -> EdgeModelListResponse:
    models = _dashboard.system_provider.get_edge_models()
    validated = _validate_collection(EdgeModelItem, models)
    return EdgeModelListResponse(models=validated, total=len(validated))


@dashboard_router.websocket("/dashboard/ws")
async def dashboard_websocket(websocket: WebSocket) -> None:
    await _ws_manager.connect(websocket)
    try:
        await _ws_manager.send_to(
            websocket,
            "metrics_update",
            {"connections": _ws_manager.get_connection_count()},
        )
        while True:
            try:
                _ = await websocket.receive_text()
            except Exception:
                await asyncio.sleep(1.0)
                await _ws_manager.send_to(
                    websocket,
                    "alert",
                    {"alerts": _dashboard.alert_manager.get_alert_counts()},
                )
    except WebSocketDisconnect:
        await _ws_manager.disconnect(websocket)
    except Exception:
        await _ws_manager.disconnect(websocket)
