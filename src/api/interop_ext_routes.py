"""Extended interoperability API routes for Phase 16 coalition standards."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from services.interop import (
    CoalitionDashboardProvider,
    ExerciseManager,
    InteropRegistry,
    InteropVerifier,
)
from src.api.interop_ext_models import (
    C2SIMOrderRequest,
    C2SIMReportRequest,
    CoalitionCOPResponse,
    DISEntityResponse,
    ExerciseCreateRequest,
    ExerciseInjectRequest,
    ExerciseOverviewResponse,
    ExerciseResponse,
    ExerciseStartRequest,
    ForceStructureResponse,
    InteropMetricsResponse,
    MSDLExportResponse,
    MSDLImportRequest,
    ORBATAddUnitRequest,
    ORBATCreateForceRequest,
    ORBATResponse,
    PublishEntityRequest,
    VerificationResponse,
)

interop_ext_router = APIRouter()
_exercise_manager = ExerciseManager()
_dashboard = CoalitionDashboardProvider(_exercise_manager)
_verifier = InteropVerifier()
_registry = InteropRegistry()


def _exercise_response(session) -> ExerciseResponse:
    return ExerciseResponse(**session.to_dict())


@interop_ext_router.post("/interop/exercises", response_model=ExerciseResponse)
async def create_exercise(req: ExerciseCreateRequest) -> ExerciseResponse:
    session = _exercise_manager.create_exercise(
        name=req.name,
        description=req.description,
        nations=req.nations,
        dis_config=req.dis_config,
        c2sim_config=req.c2sim_config,
    )
    return _exercise_response(session)


@interop_ext_router.get("/interop/exercises", response_model=List[ExerciseResponse])
async def list_exercises() -> List[ExerciseResponse]:
    return [_exercise_response(ex) for ex in _exercise_manager._exercises.values()]


@interop_ext_router.post("/interop/exercises/{exercise_id}/start")
async def start_exercise(exercise_id: int, req: ExerciseStartRequest | None = None) -> Dict[str, Any]:
    _ = req
    ok = _exercise_manager.start_exercise(exercise_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Exercise not found: {exercise_id}")
    return {"exercise_id": exercise_id, "status": "active"}


@interop_ext_router.post("/interop/exercises/{exercise_id}/pause")
async def pause_exercise(exercise_id: int) -> Dict[str, Any]:
    session = _exercise_manager.get_exercise(exercise_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Exercise not found: {exercise_id}")
    _exercise_manager.pause_exercise(exercise_id)
    return {"exercise_id": exercise_id, "status": "paused"}


@interop_ext_router.post("/interop/exercises/{exercise_id}/resume")
async def resume_exercise(exercise_id: int) -> Dict[str, Any]:
    session = _exercise_manager.get_exercise(exercise_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Exercise not found: {exercise_id}")
    _exercise_manager.resume_exercise(exercise_id)
    return {"exercise_id": exercise_id, "status": "active"}


@interop_ext_router.post("/interop/exercises/{exercise_id}/end")
async def end_exercise(exercise_id: int) -> Dict[str, Any]:
    session = _exercise_manager.get_exercise(exercise_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Exercise not found: {exercise_id}")
    return _exercise_manager.end_exercise(exercise_id)


@interop_ext_router.post("/interop/exercises/{exercise_id}/inject")
async def inject_exercise(exercise_id: int, req: ExerciseInjectRequest) -> Dict[str, Any]:
    session = _exercise_manager.get_exercise(exercise_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Exercise not found: {exercise_id}")
    _exercise_manager.inject_scenario(exercise_id, req.scenario)
    return {"exercise_id": exercise_id, "injected": True}


@interop_ext_router.get("/interop/exercises/{exercise_id}/entities", response_model=List[DISEntityResponse])
async def exercise_entities(exercise_id: int) -> List[DISEntityResponse]:
    session = _exercise_manager.get_exercise(exercise_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Exercise not found: {exercise_id}")
    rows = _exercise_manager.get_exercise_entities(exercise_id)
    return [DISEntityResponse(entities=rows, total=len(rows))]


@interop_ext_router.get("/interop/exercises/{exercise_id}/overview", response_model=ExerciseOverviewResponse)
async def exercise_overview(exercise_id: int) -> ExerciseOverviewResponse:
    payload = _dashboard.get_exercise_overview(str(exercise_id))
    return ExerciseOverviewResponse(**payload)


@interop_ext_router.post("/interop/dis/publish")
async def publish_dis(req: PublishEntityRequest, exercise_id: int = Query(default=1, ge=1)) -> Dict[str, Any]:
    ok = _exercise_manager.publish_entity(exercise_id, req.entity)
    return {"exercise_id": exercise_id, "published": ok}


@interop_ext_router.get("/interop/dis/entities", response_model=List[DISEntityResponse])
async def dis_entities() -> List[DISEntityResponse]:
    rows = _exercise_manager.dis_engine.receive_entities()
    return [DISEntityResponse(entities=rows, total=len(rows))]


@interop_ext_router.get("/interop/dis/stats")
async def dis_stats() -> Dict[str, Any]:
    return _exercise_manager.dis_engine.network.get_exercise_stats()


@interop_ext_router.post("/interop/c2sim/order")
async def c2sim_order(req: C2SIMOrderRequest) -> Dict[str, Any]:
    payload = req.model_dump()
    return _exercise_manager.c2sim_engine.send_order(payload)


@interop_ext_router.post("/interop/c2sim/report")
async def c2sim_report(req: C2SIMReportRequest) -> Dict[str, Any]:
    payload = req.model_dump()
    return _exercise_manager.c2sim_engine.send_report(payload)


@interop_ext_router.get("/interop/c2sim/messages")
async def c2sim_messages() -> List[Dict[str, Any]]:
    return _exercise_manager.c2sim_engine.receive_messages()


@interop_ext_router.post("/interop/orbat/forces", response_model=ForceStructureResponse)
async def create_orbat_force(req: ORBATCreateForceRequest) -> ForceStructureResponse:
    force = _exercise_manager.orbat_manager.create_force(req.name, req.affiliation, req.country_code)
    return ForceStructureResponse(**force.to_dict())


@interop_ext_router.post("/interop/orbat/forces/{force_id}/units", response_model=ORBATResponse)
async def add_orbat_unit(force_id: str, req: ORBATAddUnitRequest) -> ORBATResponse:
    manager = _exercise_manager.orbat_manager
    force = manager.get_force(force_id)
    if force is None:
        raise HTTPException(status_code=404, detail=f"Force not found: {force_id}")
    unit = manager.create_unit(
        name=req.name,
        designation=req.designation,
        echelon=req.echelon,
        unit_type=req.unit_type,
        affiliation=req.affiliation,
        country_code=req.country_code,
        parent_unit_id=req.parent_unit_id,
    )
    unit.strength = req.strength
    unit.equipment = req.equipment
    unit.position = tuple(req.position) if req.position else None
    unit.commander = req.commander
    manager.add_unit(force_id, unit)
    return ORBATResponse(**unit.to_dict())


@interop_ext_router.get("/interop/orbat/forces", response_model=List[ForceStructureResponse])
async def list_orbat_forces() -> List[ForceStructureResponse]:
    return [ForceStructureResponse(**force.to_dict()) for force in _exercise_manager.orbat_manager.get_all_forces()]


@interop_ext_router.get("/interop/orbat/forces/{force_id}/hierarchy")
async def orbat_hierarchy(force_id: str) -> Dict[str, Any]:
    manager = _exercise_manager.orbat_manager
    force = manager.get_force(force_id)
    if force is None:
        raise HTTPException(status_code=404, detail=f"Force not found: {force_id}")
    return _dashboard.get_orbat_view(force_id)


@interop_ext_router.post("/interop/orbat/template/saudi", response_model=ForceStructureResponse)
async def saudi_template() -> ForceStructureResponse:
    force = _exercise_manager.orbat_manager.create_saudi_template()
    return ForceStructureResponse(**force.to_dict())


@interop_ext_router.post("/interop/msdl/import")
async def import_msdl(req: MSDLImportRequest) -> Dict[str, Any]:
    manager = _exercise_manager.orbat_manager
    if req.xml_str:
        manager.from_msdl(req.xml_str)
    elif req.filepath:
        text = open(req.filepath, "r", encoding="utf-8").read()
        manager.from_msdl(text)
    else:
        raise HTTPException(status_code=400, detail="xml_str or filepath required")
    return {"imported_forces": len(manager.get_all_forces())}


@interop_ext_router.post("/interop/msdl/export", response_model=MSDLExportResponse)
async def export_msdl() -> MSDLExportResponse:
    xml = _exercise_manager.orbat_manager.to_msdl()
    return MSDLExportResponse(xml=xml, force_count=len(_exercise_manager.orbat_manager.get_all_forces()))


@interop_ext_router.post("/interop/verify", response_model=VerificationResponse)
async def verify_interop() -> VerificationResponse:
    payload = _verifier.run_full_verification()
    return VerificationResponse(**payload)


@interop_ext_router.get("/interop/coalition/cop", response_model=CoalitionCOPResponse)
async def coalition_cop() -> CoalitionCOPResponse:
    payload = _dashboard.get_coalition_cop()
    return CoalitionCOPResponse(**payload)


@interop_ext_router.get("/interop/metrics", response_model=InteropMetricsResponse)
async def interop_metrics() -> InteropMetricsResponse:
    return InteropMetricsResponse(**_dashboard.get_interop_metrics())


@interop_ext_router.get("/interop/status")
async def interop_status() -> Dict[str, Any]:
    return {
        "exercise_manager": _exercise_manager.health_check(),
        "dashboard": _dashboard.get_interop_metrics(),
        "registry": _registry.health_check(),
    }


@interop_ext_router.get("/interop/partners")
async def interop_partners() -> Dict[str, Any]:
    return {"gcc": _registry.get_gcc_partner_codes(), "nato": _registry.get_nato_partner_codes()}
