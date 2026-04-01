"""FastAPI routes for S3M Phase 20 personnel & readiness layer."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from apps.readiness import (
    Branch,
    ClearanceLevel,
    MedicalStatus,
    MilitaryStatus,
    Rank,
    ReadinessManager,
)
from src.api.readiness_models import (
    AddSlotRequest,
    CertResponse,
    CoalitionRegisterRequest,
    CoalitionRosterResponse,
    CreateUnitRequest,
    EligibilityResponse,
    FillSlotRequest,
    ForceReadinessResponse,
    IssueCertRequest,
    ManningBoardResponse,
    MemberProfileResponse,
    MemberResponse,
    PromoteRequest,
    ReadinessOverviewResponse,
    ReadinessReportResponse,
    ReadinessScoreResponse,
    RegisterMemberRequest,
    UnitDetailResponse,
    UnitManningResponse,
    UpdateMedicalRequest,
    UpdateStatusRequest,
)


readiness_router = APIRouter()
_readiness = ReadinessManager()


@readiness_router.post("/readiness/personnel", response_model=MemberResponse)
async def register_member(req: RegisterMemberRequest) -> MemberResponse:
    try:
        member = _readiness.register_member(
            name_en=req.name_en,
            name_ar=req.name_ar,
            rank=Rank(req.rank),
            branch=Branch(req.branch),
            mos=req.mos,
            mos_description_en=req.mos_desc_en,
            mos_description_ar=req.mos_desc_ar,
            unit_id=req.unit_id,
            unit_name_en=req.unit_name_en,
            unit_name_ar=req.unit_name_ar,
            service_number=req.service_number,
            clearance=ClearanceLevel(req.clearance),
            medical=MedicalStatus(req.medical),
            languages=req.languages,
            specializations=req.specializations,
        )
        return MemberResponse(**member.to_safe_dict())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@readiness_router.get("/readiness/personnel", response_model=List[MemberResponse])
async def list_personnel(
    unit: Optional[str] = Query(default=None),
    rank: Optional[str] = Query(default=None),
    branch: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    mos: Optional[str] = Query(default=None),
    deployable: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=50000),
) -> List[MemberResponse]:
    members = _readiness.personnel_registry.get_members(
        unit_id=unit,
        rank=rank,
        branch=branch,
        status=status,
        mos=mos,
        deployable_only=deployable,
    )
    return [MemberResponse(**row.to_safe_dict()) for row in members[:limit]]


@readiness_router.get("/readiness/personnel/search", response_model=List[MemberResponse])
async def search_personnel(query: str = Query(..., min_length=1)) -> List[MemberResponse]:
    rows = _readiness.search(query)
    return [MemberResponse(**row.to_safe_dict()) for row in rows]


@readiness_router.get("/readiness/personnel/{id}", response_model=MemberProfileResponse)
async def get_member_profile(id: str) -> MemberProfileResponse:
    try:
        return MemberProfileResponse(**_readiness.dashboard_provider.get_member_profile(id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@readiness_router.post("/readiness/personnel/{id}/promote", response_model=MemberResponse)
async def promote_member(id: str, req: PromoteRequest) -> MemberResponse:
    if id != req.member_id:
        raise HTTPException(status_code=400, detail="path member_id mismatch")
    try:
        member = _readiness.promote(id, Rank(req.new_rank))
        return MemberResponse(**member.to_safe_dict())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@readiness_router.patch("/readiness/personnel/{id}/status", response_model=MemberResponse)
async def update_member_status(id: str, req: UpdateStatusRequest) -> MemberResponse:
    try:
        member = _readiness.personnel_registry.update_status(id, MilitaryStatus(req.status))
        return MemberResponse(**member.to_safe_dict())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@readiness_router.patch("/readiness/personnel/{id}/medical", response_model=MemberResponse)
async def update_member_medical(id: str, req: UpdateMedicalRequest) -> MemberResponse:
    try:
        member = _readiness.personnel_registry.update_medical(id, MedicalStatus(req.medical))
        return MemberResponse(**member.to_safe_dict())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@readiness_router.post("/readiness/personnel/template/battalion")
async def create_battalion_template() -> dict:
    out = _readiness.create_saudi_battalion()
    return {"count": out["personnel"], "unit_id": out["unit"], "fill_rate": out["fill_rate"]}


@readiness_router.post("/readiness/certifications", response_model=CertResponse)
async def issue_certification(req: IssueCertRequest) -> CertResponse:
    try:
        cert = _readiness.issue_certification(
            member_id=req.member_id,
            certification_type=req.type,
            name_en=req.name_en,
            name_ar=req.name_ar,
            issuing_authority=req.authority,
            score=req.score,
            expiry_days=req.expiry_days,
            course_id=req.course_id,
            exercise_id=None,
        )
        return CertResponse(**cert.to_dict())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@readiness_router.get("/readiness/certifications/expiring")
async def get_expiring_certs(days: int = Query(default=30, ge=1, le=3650)) -> List[CertResponse]:
    rows = _readiness.certification_manager.get_expiring_soon(days)
    return [CertResponse(**row.to_dict()) for row in rows]


@readiness_router.get("/readiness/certifications/expired")
async def get_expired_certs() -> List[CertResponse]:
    rows = _readiness.certification_manager.get_expired()
    return [CertResponse(**row.to_dict()) for row in rows]


@readiness_router.get("/readiness/certifications/{member_id}")
async def get_member_certs(member_id: str) -> List[CertResponse]:
    rows = _readiness.get_certifications(member_id)
    return [CertResponse(**row.to_dict()) for row in rows]


@readiness_router.post("/readiness/certifications/types")
async def list_standard_cert_types() -> List[dict]:
    return _readiness.certification_manager.create_standard_cert_types()


@readiness_router.post("/readiness/certifications/sync")
async def sync_certifications() -> dict:
    return _readiness.certification_manager.sync_from_training_portal()


@readiness_router.post("/readiness/units", response_model=UnitManningResponse)
async def create_unit(req: CreateUnitRequest) -> UnitManningResponse:
    unit = _readiness.create_unit(
        unit_name_en=req.name_en,
        unit_name_ar=req.name_ar,
        authorized_strength=req.authorized_strength,
        orbat_unit_id=req.orbat_unit_id,
    )
    return UnitManningResponse(**unit.to_dict())


@readiness_router.get("/readiness/units")
async def list_units() -> List[dict]:
    rows = []
    for unit in _readiness.unit_manning_manager.get_units():
        rows.append(
            {
                "unit_id": unit.unit_id,
                "name_en": unit.unit_name_en,
                "name_ar": unit.unit_name_ar,
                "fill_rate": round(unit.fill_rate() * 100.0, 2),
            }
        )
    return rows


@readiness_router.get("/readiness/units/vacancies")
async def list_critical_vacancies() -> List[dict]:
    return _readiness.unit_manning_manager.get_critical_vacancies()


@readiness_router.get("/readiness/units/{id}", response_model=UnitDetailResponse)
async def get_unit_detail(id: str) -> UnitDetailResponse:
    try:
        return UnitDetailResponse(**_readiness.get_unit_detail(id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@readiness_router.post("/readiness/units/{id}/slots")
async def add_slot(id: str, req: AddSlotRequest) -> dict:
    if id != req.unit_id:
        raise HTTPException(status_code=400, detail="path unit_id mismatch")
    slot = _readiness.unit_manning_manager.add_slot(
        unit_id=id,
        position_title_en=req.position_title_en,
        position_title_ar=req.position_title_ar,
        required_rank=Rank(req.required_rank),
        required_mos=req.required_mos,
        required_clearance=ClearanceLevel(req.required_clearance),
        required_certs=req.required_certs,
    )
    return slot.to_dict()


@readiness_router.post("/readiness/units/{id}/fill")
async def fill_slot(id: str, req: FillSlotRequest) -> dict:
    if id != req.unit_id:
        raise HTTPException(status_code=400, detail="path unit_id mismatch")
    ok = _readiness.fill_slot(req.slot_id, req.member_id)
    return {"filled": bool(ok), "slot_id": req.slot_id, "member_id": req.member_id}


@readiness_router.post("/readiness/units/{id}/auto-fill")
async def auto_fill_unit(id: str) -> dict:
    return _readiness.auto_fill(id)


@readiness_router.post("/readiness/units/from-orbat")
async def create_from_orbat(orbat_unit_id: str = Query(..., min_length=1)) -> UnitManningResponse:
    unit = _readiness.unit_manning_manager.create_from_orbat(orbat_unit_id)
    return UnitManningResponse(**unit.to_dict())


@readiness_router.post("/readiness/eligibility/{member_id}", response_model=EligibilityResponse)
async def evaluate_member_eligibility(member_id: str) -> EligibilityResponse:
    try:
        row = _readiness.evaluate_eligibility(member_id)
        return EligibilityResponse(**row.to_dict())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@readiness_router.post("/readiness/score/{unit_id}", response_model=ReadinessScoreResponse)
async def calculate_unit_score(unit_id: str) -> ReadinessScoreResponse:
    row = _readiness.calculate_readiness(unit_id)
    return ReadinessScoreResponse(**row.to_dict())


@readiness_router.post("/readiness/score/force", response_model=ForceReadinessResponse)
async def calculate_force_score() -> ForceReadinessResponse:
    return ForceReadinessResponse(**_readiness.calculate_force_readiness())


@readiness_router.get("/readiness/overview", response_model=ReadinessOverviewResponse)
async def readiness_overview() -> ReadinessOverviewResponse:
    return ReadinessOverviewResponse(**_readiness.get_readiness_overview())


@readiness_router.get("/readiness/manning-board", response_model=ManningBoardResponse)
async def get_manning_board() -> ManningBoardResponse:
    return ManningBoardResponse(units=_readiness.dashboard_provider.get_manning_board())


@readiness_router.post("/readiness/coalition/register")
async def register_coalition_personnel(req: CoalitionRegisterRequest) -> dict:
    try:
        count = _readiness.register_coalition_personnel(req.partner_code, req.personnel)
        return {"registered": count}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@readiness_router.get("/readiness/coalition/roster", response_model=CoalitionRosterResponse)
async def get_coalition_roster(partner_code: Optional[int] = Query(default=None)) -> CoalitionRosterResponse:
    roster = _readiness.coalition_bridge.get_coalition_roster(partner_code=partner_code)
    return CoalitionRosterResponse(roster=roster)


@readiness_router.get("/readiness/coalition/readiness")
async def get_coalition_readiness() -> dict:
    return _readiness.coalition_bridge.get_coalition_readiness()


@readiness_router.post("/readiness/report", response_model=ReadinessReportResponse)
async def generate_readiness_report(unit_id: Optional[str] = Query(default=None)) -> ReadinessReportResponse:
    report = _readiness.generate_readiness_report(unit_id=unit_id)
    return ReadinessReportResponse(report=report)


@readiness_router.post("/readiness/report/manning", response_model=ReadinessReportResponse)
async def generate_manning_report() -> ReadinessReportResponse:
    report = _readiness.generate_manning_report()
    return ReadinessReportResponse(report=report)


@readiness_router.get("/readiness/status")
async def readiness_status() -> dict:
    return _readiness.health_check()
