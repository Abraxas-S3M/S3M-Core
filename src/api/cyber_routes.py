"""FastAPI routes for S3M Phase 13 Cyber Defense Operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from services.cyber import (
    CaseSeverity,
    CaseVerdict,
    EnrichmentResult,
    Observable,
    ObservableType,
    SOCManager,
)
from src.api.cyber_models import (
    AlertQueueResponse,
    CaseCreateRequest,
    CaseResponse,
    CaseUpdateRequest,
    EnrichmentResponse,
    ExerciseCreateRequest,
    ExerciseScoreResponse,
    LogSearchRequest,
    LogSearchResponse,
    MITREHeatmapResponse,
    ObservableCreateRequest,
    PlatformStatusResponse,
    PlaybookExecuteRequest,
    PlaybookResponse,
    SOCOverviewResponse,
    SOCReportResponse,
    TriageEventRequest,
    TriageResponse,
)
from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource


cyber_router = APIRouter()
_soc = SOCManager()
_exercise_scores: Dict[str, dict] = {}


def _to_threat_event(req: TriageEventRequest) -> ThreatEvent:
    return ThreatEvent(
        source=ThreatSource.from_value(req.source),
        level=ThreatLevel.from_value(req.level),
        category=ThreatCategory.from_value(req.category),
        title=req.title,
        description=req.description,
        raw_data=req.raw_data,
        confidence=req.confidence,
    )


@cyber_router.post("/cyber/triage", response_model=TriageResponse)
async def cyber_triage(req: TriageEventRequest | dict) -> TriageResponse:
    try:
        payload = req if isinstance(req, dict) else req.model_dump()
        # Accept both flat event payload and wrapped {"event": {...}} payloads.
        if "event" in payload and isinstance(payload["event"], dict):
            event_payload = payload["event"]
        else:
            event_payload = payload
        event_req = TriageEventRequest(**event_payload)
        event = _to_threat_event(event_req)
        triage = _soc.alert_triage.triage(event)
        return TriageResponse(
            event_id=triage["event_id"],
            severity=triage["severity"].value,
            observables=[obs.to_dict() for obs in triage["observables"]],
            mitre=triage["mitre"].to_dict() if triage["mitre"] else None,
            triage_score=triage["triage_score"],
            auto_create_case=triage["auto_create_case"],
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@cyber_router.post("/cyber/cases", response_model=CaseResponse)
async def create_case(req: CaseCreateRequest) -> CaseResponse:
    try:
        case = _soc.case_manager.create_case(
            title=req.title,
            description=req.description,
            severity=CaseSeverity.from_value(req.severity),
            source_events=req.source_events,
            observables=[],
            mitre_tactics=[],
            mitre_techniques=[],
        )
        return CaseResponse(**case.to_dict())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@cyber_router.get("/cyber/cases", response_model=List[CaseResponse])
async def list_cases(
    status: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    analyst: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
) -> List[CaseResponse]:
    try:
        cases = _soc.get_cases(status=status, severity=severity, analyst=analyst, limit=limit)
        return [CaseResponse(**case.to_dict()) for case in cases]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@cyber_router.get("/cyber/cases/{case_id}", response_model=CaseResponse)
async def case_detail(case_id: str) -> CaseResponse:
    case = _soc.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    return CaseResponse(**case.to_dict())


@cyber_router.patch("/cyber/cases/{case_id}", response_model=CaseResponse)
async def update_case(case_id: str, req: CaseUpdateRequest) -> CaseResponse:
    case = _soc.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    try:
        updates: Dict[str, Any] = {}
        if req.status is not None:
            updates["status"] = req.status
        if req.assigned_analyst is not None:
            updates["assigned_analyst"] = req.assigned_analyst
        if req.tags is not None:
            updates["tags"] = req.tags
        if updates:
            _soc.case_manager.update_case(case_id, **updates)
        if req.escalate_reason:
            _soc.escalate_case(case_id, req.escalate_reason)
        if req.add_note:
            case.add_timeline_entry("analyst_note", req.assigned_analyst or "analyst", req.add_note)
        return CaseResponse(**case.to_dict())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@cyber_router.post("/cyber/cases/{case_id}/resolve", response_model=CaseResponse)
async def resolve_case(case_id: str, body: dict[str, str]) -> CaseResponse:
    if "verdict" not in body:
        raise HTTPException(status_code=400, detail="verdict is required")
    notes = body.get("notes", "Resolved via API")
    try:
        case = _soc.resolve_case(case_id, CaseVerdict.from_value(body["verdict"]), notes)
        return CaseResponse(**case.to_dict())
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@cyber_router.post("/cyber/cases/{case_id}/enrich", response_model=EnrichmentResponse)
async def enrich_case(case_id: str) -> EnrichmentResponse:
    case = _soc.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    try:
        enrichments = _soc.ir_bridge.enrich_observables_from_dicts(case.observables)
        for enrichment in enrichments:
            _soc.case_manager.add_enrichment(case_id, enrichment)
        return EnrichmentResponse(
            case_id=case_id,
            enrichments=[item.to_dict() for item in enrichments],
            total=len(enrichments),
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@cyber_router.get("/cyber/cases/{case_id}/observables")
async def list_observables(case_id: str) -> List[dict]:
    case = _soc.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    return case.observables


@cyber_router.post("/cyber/cases/{case_id}/observables")
async def add_observable(case_id: str, req: ObservableCreateRequest) -> dict:
    case = _soc.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    try:
        observable = Observable(
            observable_type=ObservableType.from_value(req.observable_type),
            value=req.value,
            source_case_id=case_id,
            tags=req.tags,
            tlp=req.tlp,
        )
        _soc.case_manager.add_observable(case_id, observable)
        return observable.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@cyber_router.get("/cyber/playbooks")
async def list_playbooks() -> List[dict]:
    return _soc.soar_engine.get_playbooks()


@cyber_router.post("/cyber/cases/{case_id}/playbook", response_model=PlaybookResponse)
async def run_playbook(case_id: str, req: PlaybookExecuteRequest) -> PlaybookResponse:
    case = _soc.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case not found: {case_id}")
    try:
        _soc.soar_engine.register_case(case)
        result = _soc.soar_engine.manual_execute(case_id, req.playbook_id)
        return PlaybookResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@cyber_router.get("/cyber/soar/history")
async def soar_history(limit: int = Query(default=50, ge=1, le=500)) -> List[dict]:
    return _soc.soar_engine.get_history()[:limit]


@cyber_router.get("/cyber/soc/overview", response_model=SOCOverviewResponse)
async def soc_overview() -> SOCOverviewResponse:
    return SOCOverviewResponse(**_soc.soc_dashboard.get_soc_overview())


@cyber_router.get("/cyber/soc/alerts", response_model=AlertQueueResponse)
async def soc_alerts(
    severity: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> AlertQueueResponse:
    alerts = _soc.soc_dashboard.get_alert_queue(severity=severity, limit=limit)
    return AlertQueueResponse(alerts=alerts, total=len(alerts))


@cyber_router.get("/cyber/soc/mitre-heatmap", response_model=MITREHeatmapResponse)
async def soc_mitre_heatmap() -> MITREHeatmapResponse:
    rows = _soc.soc_dashboard.get_mitre_heatmap()
    return MITREHeatmapResponse(heatmap=rows, total=len(rows))


@cyber_router.get("/cyber/soc/ioc-feed")
async def soc_ioc_feed(limit: int = Query(default=100, ge=1, le=1000)) -> List[dict]:
    return _soc.soc_dashboard.get_ioc_feed(limit=limit)


@cyber_router.post("/cyber/logs/search", response_model=LogSearchResponse)
async def log_search(req: LogSearchRequest) -> LogSearchResponse:
    rows = _soc.log_aggregator.search(req.query, backend=req.backend)
    return LogSearchResponse(query=req.query, backend=req.backend, results=rows, total=len(rows))


@cyber_router.post("/cyber/training/exercise", response_model=ExerciseScoreResponse)
async def create_training_exercise(req: ExerciseCreateRequest) -> ExerciseScoreResponse:
    try:
        exercise = _soc.cyber_training.create_exercise(req.scenario_type)
        score = _soc.cyber_training.run_exercise(exercise["events"])
        _exercise_scores[score["exercise_id"]] = score
        return ExerciseScoreResponse(**score)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@cyber_router.get("/cyber/training/exercises")
async def list_training_exercises() -> List[dict]:
    return _soc.cyber_training.get_exercise_history()


@cyber_router.get("/cyber/training/exercises/{exercise_id}/score")
async def get_training_score(exercise_id: str) -> dict:
    if exercise_id in _exercise_scores:
        return _exercise_scores[exercise_id]
    return _soc.cyber_training.evaluate_response(exercise_id)


@cyber_router.get("/cyber/platforms/status", response_model=PlatformStatusResponse)
async def platform_status() -> PlatformStatusResponse:
    status = _soc.ir_bridge.get_platform_status()
    return PlatformStatusResponse(**status)


@cyber_router.post("/cyber/soc/report", response_model=SOCReportResponse)
async def soc_report() -> SOCReportResponse:
    return SOCReportResponse(report=_soc.generate_soc_report())
