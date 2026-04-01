"""FastAPI routes for Phase 19 Intelligence & OSINT Briefings."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from src.api.intel_models import (
    CollectResponse,
    CrisisBoardResponse,
    CrisisCreateRequest,
    CrisisEventResponse,
    CrisisUpdateRequest,
    DailyBriefResponse,
    GenerateBriefRequest,
    GenerateReportRequest,
    IndicatorCreateRequest,
    IntelOverviewResponse,
    IntelReportResponse,
    IntelSourceResponse,
    OSINTItemListResponse,
    OSINTItemResponse,
    RegionIntelResponse,
    SourceHealthResponse,
    SourceListResponse,
    WarningIndicatorResponse,
    WeeklyEstimateResponse,
)
from src.apps.intel import IntelManager

intel_router = APIRouter()
_intel = IntelManager()


def _as_http_error(exc: Exception, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=str(exc))


# Collection
@intel_router.post("/intel/collect", response_model=CollectResponse)
async def intel_collect() -> CollectResponse:
    try:
        result = _intel.collect_and_analyze()
    except Exception as exc:
        raise _as_http_error(exc) from exc
    return CollectResponse(**result)


@intel_router.get("/intel/items", response_model=OSINTItemListResponse)
async def intel_items(
    query: Optional[str] = Query(default=None),
    region: Optional[str] = Query(default=None),
    topic: Optional[str] = Query(default=None),
    min_relevance: float = Query(default=0.0, ge=0.0, le=1.0),
    since: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> OSINTItemListResponse:
    try:
        if query:
            items = _intel.search_intel(query)
            if region:
                items = [item for item in items if any(region.lower() in r.lower() for r in item.regions)]
            if topic:
                items = [item for item in items if any(topic.lower() in t.lower() for t in item.topics)]
            items = [item for item in items if item.relevance_score >= min_relevance][:limit]
        else:
            items = _intel.collector.get_items(
                region=region,
                topic=topic,
                min_relevance=min_relevance,
                since=since,
                limit=limit,
            )
    except Exception as exc:
        raise _as_http_error(exc) from exc
    return OSINTItemListResponse(items=[OSINTItemResponse(**item.to_dict()) for item in items], total=len(items))


@intel_router.get("/intel/items/{item_id}", response_model=OSINTItemResponse)
async def intel_item_detail(item_id: str) -> OSINTItemResponse:
    items = _intel.collector.get_items(limit=100000)
    for item in items:
        if item.item_id == item_id:
            return OSINTItemResponse(**item.to_dict())
    raise HTTPException(status_code=404, detail=f"OSINT item not found: {item_id}")


# Sources
@intel_router.get("/intel/sources", response_model=SourceListResponse)
async def intel_sources() -> SourceListResponse:
    sources = _intel.collector.source_manager.get_sources(active_only=False)
    return SourceListResponse(
        sources=[IntelSourceResponse(**source.to_dict()) for source in sources],
        total=len(sources),
    )


@intel_router.post("/intel/sources", response_model=IntelSourceResponse)
async def intel_register_source(body: dict[str, Any]) -> IntelSourceResponse:
    try:
        source = _intel.collector.source_manager.register_source(
            name=str(body.get("name", "")),
            source_type=str(body.get("source_type", "NEWS_FEED")),
            reliability=str(body.get("reliability", "F_UNKNOWN")),
            regions=list(body.get("regions", [])),
            topics=list(body.get("topics", [])),
            language=str(body.get("language", "en")),
            frequency=str(body.get("frequency", "manual")),
            data_path=body.get("data_path"),
        )
        return IntelSourceResponse(**source.to_dict())
    except Exception as exc:
        raise _as_http_error(exc) from exc


@intel_router.post("/intel/sources/defaults", response_model=SourceListResponse)
async def intel_sources_defaults() -> SourceListResponse:
    try:
        _intel.collector.source_manager.create_default_sources()
        all_sources = _intel.collector.source_manager.get_sources(active_only=False)
    except Exception as exc:
        raise _as_http_error(exc) from exc
    return SourceListResponse(
        sources=[IntelSourceResponse(**source.to_dict()) for source in all_sources],
        total=len(all_sources),
    )


@intel_router.get("/intel/sources/health", response_model=SourceHealthResponse)
async def intel_source_health() -> SourceHealthResponse:
    sources = _intel.dashboard.get_source_health()
    return SourceHealthResponse(sources=sources, total=len(sources))


# Briefings
@intel_router.post("/intel/brief/daily", response_model=DailyBriefResponse)
async def intel_daily_brief(req: GenerateBriefRequest | None = None) -> DailyBriefResponse:
    try:
        brief = _intel.generate_daily_brief(date=req.date if req else None)
    except Exception as exc:
        raise _as_http_error(exc) from exc
    return DailyBriefResponse(**brief.to_dict())


@intel_router.post("/intel/brief/weekly", response_model=WeeklyEstimateResponse)
async def intel_weekly_estimate(req: GenerateBriefRequest | None = None) -> WeeklyEstimateResponse:
    try:
        estimate = _intel.generate_weekly_estimate(week=req.week if req else None)
    except Exception as exc:
        raise _as_http_error(exc) from exc
    return WeeklyEstimateResponse(**estimate.to_dict())


@intel_router.post("/intel/report/sitrep", response_model=IntelReportResponse)
async def intel_report_sitrep(req: GenerateReportRequest) -> IntelReportResponse:
    if not req.region:
        raise HTTPException(status_code=400, detail="region is required for SITREP")
    report = _intel.generate_sitrep(req.region)
    return IntelReportResponse(**report.to_dict())


@intel_router.post("/intel/report/intsum", response_model=IntelReportResponse)
async def intel_report_intsum(req: GenerateReportRequest | None = None) -> IntelReportResponse:
    report = _intel.generate_intsum(period=req.period if req and req.period else "24h")
    return IntelReportResponse(**report.to_dict())


@intel_router.post("/intel/report/threat", response_model=IntelReportResponse)
async def intel_report_threat(req: GenerateReportRequest) -> IntelReportResponse:
    if not req.region or not req.topic:
        raise HTTPException(status_code=400, detail="region and topic are required for threat assessment")
    report = _intel.generate_threat_assessment(req.region, req.topic)
    return IntelReportResponse(**report.to_dict())


@intel_router.get("/intel/reports", response_model=list[IntelReportResponse])
async def intel_reports(
    report_type: Optional[str] = Query(default=None),
    region: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=1000),
) -> list[IntelReportResponse]:
    reports = _intel.briefing.product_factory.list_reports()
    if report_type:
        reports = [r for r in reports if r.report_type.value == report_type]
    if region:
        reports = [r for r in reports if region in r.regions]
    reports = reports[-limit:]
    return [IntelReportResponse(**report.to_dict()) for report in reports]


@intel_router.get("/intel/reports/{report_id}", response_model=IntelReportResponse)
async def intel_report_detail(report_id: str) -> IntelReportResponse:
    for report in _intel.briefing.product_factory.list_reports():
        if report.report_id == report_id:
            return IntelReportResponse(**report.to_dict())
    raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")


# Monitoring
@intel_router.get("/intel/crises", response_model=list[CrisisEventResponse])
async def intel_crises() -> list[CrisisEventResponse]:
    crises = _intel.get_crises()
    return [CrisisEventResponse(**crisis.to_dict()) for crisis in crises]


@intel_router.post("/intel/crises", response_model=CrisisEventResponse)
async def intel_create_crisis(req: CrisisCreateRequest) -> CrisisEventResponse:
    try:
        crisis = _intel.monitor.crisis_tracker.create_crisis(
            name=req.name,
            description=req.description,
            severity=req.severity,
            region=req.region,
        )
    except Exception as exc:
        raise _as_http_error(exc) from exc
    return CrisisEventResponse(**crisis.to_dict())


@intel_router.patch("/intel/crises/{event_id}", response_model=CrisisEventResponse)
async def intel_update_crisis(event_id: str, req: CrisisUpdateRequest) -> CrisisEventResponse:
    tracker = _intel.monitor.crisis_tracker
    if tracker.get_crisis(event_id) is None:
        raise HTTPException(status_code=404, detail=f"Crisis not found: {event_id}")
    action = (req.action or "").lower().strip()
    try:
        if action == "resolve":
            crisis = tracker.resolve(event_id, req.description)
        elif action in {"escalate", "de_escalate", "de-escalate"}:
            crisis = tracker.update_crisis(event_id, req.description, severity_change=action)
        else:
            crisis = tracker.update_crisis(event_id, req.description, severity_change=req.severity_change)
    except Exception as exc:
        raise _as_http_error(exc) from exc
    return CrisisEventResponse(**crisis.to_dict())


@intel_router.get("/intel/warnings", response_model=list[WarningIndicatorResponse])
async def intel_warnings() -> list[WarningIndicatorResponse]:
    warnings = _intel.monitor.early_warning.get_active_warnings()
    return [WarningIndicatorResponse(**indicator.to_dict()) for indicator in warnings]


@intel_router.post("/intel/warnings", response_model=WarningIndicatorResponse)
async def intel_create_warning(req: IndicatorCreateRequest) -> WarningIndicatorResponse:
    indicator = _intel.monitor.early_warning.create_indicator(
        name=req.name,
        description=req.description,
        region=req.region,
        topic=req.topic,
        threshold=req.threshold,
    )
    return WarningIndicatorResponse(**indicator.to_dict())


@intel_router.post("/intel/warnings/defaults", response_model=list[WarningIndicatorResponse])
async def intel_warning_defaults() -> list[WarningIndicatorResponse]:
    _intel.monitor.early_warning.create_default_indicators()
    indicators = _intel.monitor.early_warning.indicators()
    return [WarningIndicatorResponse(**indicator.to_dict()) for indicator in indicators]


# Dashboard
@intel_router.get("/intel/overview", response_model=IntelOverviewResponse)
async def intel_overview() -> IntelOverviewResponse:
    return IntelOverviewResponse(**_intel.get_intel_overview())


@intel_router.get("/intel/region/{region}", response_model=RegionIntelResponse)
async def intel_region(region: str) -> RegionIntelResponse:
    return RegionIntelResponse(**_intel.get_region_intel(region))


@intel_router.get("/intel/crises/board", response_model=CrisisBoardResponse)
async def intel_crisis_board() -> CrisisBoardResponse:
    return CrisisBoardResponse(board=_intel.dashboard.get_crisis_board())


@intel_router.get("/intel/status")
async def intel_status() -> dict[str, Any]:
    return _intel.health_check()
