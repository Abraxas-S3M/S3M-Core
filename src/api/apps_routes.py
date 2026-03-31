"""FastAPI routes for S3M Phase 11 domain applications."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from src.api.apps_models import (
    BenchmarkRequest,
    BenchmarkResponse,
    COAComparisonResponse,
    CorrelateRequest,
    CorrelationResponse,
    DatasetDetailResponse,
    DatasetListResponse,
    DisruptionPredictionResponse,
    DroneMissionRequest,
    DroneMissionResponse,
    EscalationResponse,
    FleetStatusResponse,
    ForecastResponse,
    IntelResponse,
    MissionBriefRequest,
    NLMissionRequest,
    OPORDResponse,
    OSINTAnalyzeRequest,
    RestockResponse,
    RiskAnalysisResponse,
    RouteOptimizeRequest,
    RouteResponse,
    SupplyDataRequest,
)
from src.apps.battle_planning import BattlePlanner
from src.apps.data_management import BenchmarkHarness, DatasetRegistry
from src.apps.drone_ops import DroneOpsModule
from src.apps.geopolitical import GeopoliticalModule
from src.apps.logistics import LogisticsModule
from src.apps.threat_hunting import ThreatHuntingModule

apps_router = APIRouter()

_battle = BattlePlanner()
_logistics = LogisticsModule()
_threats = ThreatHuntingModule()
_geo = GeopoliticalModule()
_drone = DroneOpsModule()
_registry = DatasetRegistry()
_benchmarks = BenchmarkHarness()


def _as_http_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


# Battle Planning (4)
@apps_router.post("/apps/battle/opord", response_model=OPORDResponse)
async def apps_battle_opord(req: MissionBriefRequest) -> OPORDResponse:
    try:
        if req.language == "ar":
            opord = _battle.ops_generator.generate_arabic(req.brief)
        else:
            opord = _battle.ops_generator.generate(req.brief, context=req.options or {})
        return OPORDResponse(opord=opord)
    except Exception as exc:
        raise _as_http_error(exc) from exc


@apps_router.post("/apps/battle/simulate")
async def apps_battle_simulate(req: MissionBriefRequest) -> dict[str, Any]:
    try:
        return _battle.plan(req.brief, options=req.options or {})
    except Exception as exc:
        raise _as_http_error(exc) from exc


@apps_router.post("/apps/battle/compare-coa", response_model=COAComparisonResponse)
async def apps_battle_compare_coa(req: MissionBriefRequest) -> COAComparisonResponse:
    try:
        num = int((req.options or {}).get("num_coas", 3))
        result = _battle.plan_with_comparison(req.brief, num_coas=num)
        return COAComparisonResponse(**result)
    except Exception as exc:
        raise _as_http_error(exc) from exc


@apps_router.get("/apps/battle/plans")
async def apps_battle_plans() -> dict[str, Any]:
    history = _battle.get_history()
    return {"plans": history, "total": len(history)}


# Logistics (4)
@apps_router.post("/apps/logistics/predict", response_model=DisruptionPredictionResponse)
async def apps_logistics_predict(req: SupplyDataRequest) -> DisruptionPredictionResponse:
    try:
        return DisruptionPredictionResponse(**_logistics.predict(req.records))
    except Exception as exc:
        raise _as_http_error(exc) from exc


@apps_router.post("/apps/logistics/route", response_model=RouteResponse)
async def apps_logistics_route(req: RouteOptimizeRequest) -> RouteResponse:
    try:
        result = _logistics.optimize_route(req.origin, req.destination, req.threats)
        return RouteResponse(**result)
    except Exception as exc:
        raise _as_http_error(exc) from exc


@apps_router.get("/apps/logistics/inventory")
async def apps_logistics_inventory(category: Optional[str] = None, location: Optional[str] = None) -> dict[str, Any]:
    try:
        records = _logistics.inventory_tracker.get_inventory(category=category, location=location)
        return {"items": records, "total": len(records), "stats": _logistics.inventory_tracker.get_stats()}
    except Exception as exc:
        raise _as_http_error(exc) from exc


@apps_router.post("/apps/logistics/restock-check", response_model=RestockResponse)
async def apps_logistics_restock_check() -> RestockResponse:
    try:
        items = _logistics.check_inventory()
        return RestockResponse(restock_items=items, total=len(items))
    except Exception as exc:
        raise _as_http_error(exc) from exc


# Threat Hunting (4)
@apps_router.post("/apps/threats/correlate", response_model=CorrelationResponse)
async def apps_threats_correlate(req: CorrelateRequest) -> CorrelationResponse:
    try:
        result = _threats.hunt(events=req.events)
        return CorrelationResponse(correlations=result.get("correlations", []))
    except Exception as exc:
        raise _as_http_error(exc) from exc


@apps_router.post("/apps/threats/osint/analyze", response_model=IntelResponse)
async def apps_threats_osint_analyze(req: OSINTAnalyzeRequest) -> IntelResponse:
    try:
        return IntelResponse(**_threats.analyze_osint(req.query, req.files))
    except Exception as exc:
        raise _as_http_error(exc) from exc


@apps_router.get("/apps/threats/escalations", response_model=EscalationResponse)
async def apps_threats_escalations() -> EscalationResponse:
    active = _threats.escalation.get_active_escalations()
    return EscalationResponse(escalations=active, total=len(active))


@apps_router.post("/apps/threats/escalations/rules")
async def apps_threats_escalation_rules(body: dict[str, Any]) -> dict[str, Any]:
    try:
        action = str(body.get("action", "add")).lower()
        if action == "remove":
            _threats.escalation.remove_rule(str(body.get("name", "")))
        else:
            _threats.escalation.add_rule(
                name=str(body.get("name", "")),
                condition=str(body.get("condition", "")),
                action=str(body.get("response_action", body.get("action_name", body.get("target_action", "alert_commander")))),
                auto_response=bool(body.get("auto_response", False)),
                priority=int(body.get("priority", 3)),
            )
        rules = _threats.escalation.get_rules()
        return {"rules": rules, "total": len(rules)}
    except Exception as exc:
        raise _as_http_error(exc) from exc


# Geopolitical (4)
@apps_router.post("/apps/geopolitical/analyze", response_model=RiskAnalysisResponse)
async def apps_geo_analyze(body: dict[str, Any]) -> RiskAnalysisResponse:
    try:
        result = _geo.analyze_event(description=str(body.get("description", "")), region=str(body.get("region", "")))
        return RiskAnalysisResponse(result=result)
    except Exception as exc:
        raise _as_http_error(exc) from exc


@apps_router.get("/apps/geopolitical/risks")
async def apps_geo_risks() -> dict[str, Any]:
    risks = _geo.get_risks()
    return {"risks": risks, "total": len(risks)}


@apps_router.post("/apps/geopolitical/forecast", response_model=ForecastResponse)
async def apps_geo_forecast(body: dict[str, Any]) -> ForecastResponse:
    try:
        region = str(body.get("region", ""))
        days = int(body.get("days", 30))
        return ForecastResponse(forecast=_geo.get_forecast(region, days))
    except Exception as exc:
        raise _as_http_error(exc) from exc


@apps_router.get("/apps/geopolitical/trends")
async def apps_geo_trends() -> dict[str, Any]:
    landscape = _geo.get_landscape()
    return {"trends": landscape.get("risks", {}), "summary": landscape.get("summary", "")}


# Drone Ops (4)
@apps_router.post("/apps/drone/mission", response_model=DroneMissionResponse)
async def apps_drone_mission(req: DroneMissionRequest) -> DroneMissionResponse:
    try:
        payload = {
            "mission_type": req.mission_type,
            "waypoints": req.waypoints,
            "num_agents": req.num_agents,
            "rules_of_engagement": req.roe,
            "platform_type": req.platform_type,
            "description": req.description,
        }
        result = _drone.launch_mission(payload)
        return DroneMissionResponse(
            mission=result.get("mission", {}),
            autopilot_connected=bool(result.get("autopilot_connected", False)),
            timestamp=str(result.get("timestamp", "")),
        )
    except Exception as exc:
        raise _as_http_error(exc) from exc


@apps_router.post("/apps/drone/mission/nl", response_model=DroneMissionResponse)
async def apps_drone_mission_nl(req: NLMissionRequest) -> DroneMissionResponse:
    try:
        result = _drone.launch_from_nl(req.text, language=req.language)
        return DroneMissionResponse(
            mission=result.get("mission", {}),
            autopilot_connected=bool(result.get("autopilot_connected", False)),
            timestamp=str(result.get("timestamp", "")),
        )
    except Exception as exc:
        raise _as_http_error(exc) from exc


@apps_router.get("/apps/drone/missions")
async def apps_drone_missions() -> dict[str, Any]:
    missions = _drone.get_active_missions()
    return {"missions": missions, "total": len(missions)}


@apps_router.post("/apps/drone/missions/{id}/abort")
async def apps_drone_abort(id: str) -> dict[str, Any]:
    try:
        return _drone.abort(id)
    except Exception as exc:
        raise _as_http_error(exc) from exc


# Data Management (5)
@apps_router.get("/apps/data/datasets", response_model=DatasetListResponse)
async def apps_data_datasets(domain: Optional[str] = None) -> DatasetListResponse:
    datasets = _registry.list_datasets(domain=domain)
    return DatasetListResponse(datasets=datasets, total=len(datasets))


@apps_router.get("/apps/data/datasets/{id}", response_model=DatasetDetailResponse)
async def apps_data_dataset_detail(id: str) -> DatasetDetailResponse:
    dataset = _registry.get_dataset(id)
    if not dataset:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {id}")
    return DatasetDetailResponse(dataset=dataset)


@apps_router.post("/apps/data/benchmark", response_model=BenchmarkResponse)
async def apps_data_benchmark(req: BenchmarkRequest) -> BenchmarkResponse:
    try:
        return BenchmarkResponse(**_benchmarks.run_benchmark(req.dataset_id, req.model_id, req.task))
    except Exception as exc:
        raise _as_http_error(exc) from exc


@apps_router.get("/apps/data/benchmarks")
async def apps_data_benchmarks() -> dict[str, Any]:
    entries = _benchmarks.list_benchmarks()
    return {"benchmarks": entries, "total": len(entries)}


@apps_router.get("/apps/data/stats")
async def apps_data_stats() -> dict[str, Any]:
    return {"registry": _registry.get_stats(), "availability": _registry.check_availability()}

