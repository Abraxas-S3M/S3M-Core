"""FastAPI router for Layer 12 Training & Simulation Advanced."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from apps.simulation.manager import TrainingSimManager
from apps.simulation.models import WargameConfig
from src.api.training_sim_models import (
    AssignCourseRequest,
    AssignmentResponse,
    COAWargameRequest,
    ExerciseCreateRequest,
    ExerciseResponse,
    ExerciseScoreResponse,
    LeaderboardResponse,
    OfficerProfileResponse,
    OfficerResponse,
    PortalOverviewResponse,
    QuickWargameRequest,
    ReadinessResponse,
    RegisterOfficerRequest,
    ReplayResponse,
    ScenarioFromBriefRequest,
    ScenarioFromORBATRequest,
    ScenarioResponse,
    SubmitOrdersRequest,
    TrainingReportResponse,
    TurnResultResponse,
    WargameCreateRequest,
    WargameResultResponse,
    WargameSessionResponse,
)

training_sim_router = APIRouter()
_manager = TrainingSimManager()


def _to_http(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@training_sim_router.post("/training/wargame", response_model=WargameSessionResponse)
async def create_wargame(req: WargameCreateRequest) -> WargameSessionResponse:
    try:
        if isinstance(req.blue_units_or_force_id, int):
            blue_force_id = "blue-force"
            blue_units = req.blue_units_or_force_id
        else:
            blue_force_id = str(req.blue_units_or_force_id)
            blue_units = 10

        if isinstance(req.red_units_or_force_id, int):
            red_force_id = "red-force"
            red_units = req.red_units_or_force_id
        else:
            red_force_id = str(req.red_units_or_force_id)
            red_units = 10

        config = WargameConfig(
            wargame_id=f"wg-{uuid4().hex[:10]}",
            name=req.name,
            description=f"Layer 12 wargame: {req.name}",
            wargame_type=req.type,
            scenario_id=None,
            blue_force_id=blue_force_id,
            red_force_id=red_force_id,
            turn_limit=req.turns,
            turn_duration_seconds=60.0,
            llm_adversary=req.llm_adversary,
            adversary_difficulty=req.adversary_difficulty,
            rules_of_engagement="weapons_tight",
            victory_conditions=[{"type": "eliminate", "target": "red", "threshold_pct": 75}],
            parameters={"blue_units": blue_units, "red_units": red_units, "terrain": "desert"},
        )
        session = _manager.create_wargame(config)
        return WargameSessionResponse(
            session_id=session.session_id,
            status=session.status,
            current_turn=session.current_turn,
            config=session.config.to_dict(),
            result=None,
        )
    except Exception as exc:
        raise _to_http(exc) from exc


@training_sim_router.post("/training/wargame/quick", response_model=WargameResultResponse)
async def quick_wargame(req: QuickWargameRequest) -> WargameResultResponse:
    try:
        result = _manager.run_quick_wargame(req.name, req.blue_units, req.red_units, req.turns, req.adversary)
        return WargameResultResponse(result=result.to_dict())
    except Exception as exc:
        raise _to_http(exc) from exc


@training_sim_router.post("/training/wargame/coa", response_model=Dict[str, List[dict]])
async def coa_wargame(req: COAWargameRequest) -> Dict[str, List[dict]]:
    try:
        results = _manager.wargame_suite.create_coa_wargame(req.mission_brief, req.num_coas)
        return {"results": [result.to_dict() for result in results]}
    except Exception as exc:
        raise _to_http(exc) from exc


@training_sim_router.post("/training/wargame/{id}/orders", response_model=TurnResultResponse)
async def submit_orders(id: str, req: SubmitOrdersRequest) -> TurnResultResponse:
    try:
        payload = _manager.submit_orders(id, req.orders)
        return TurnResultResponse(
            turn_number=payload["turn_number"],
            events=payload["events"],
            blue_losses=payload["blue_losses"],
            red_losses=payload["red_losses"],
            state_snapshot=payload["state_snapshot"],
        )
    except Exception as exc:
        raise _to_http(exc) from exc


@training_sim_router.get("/training/wargame/{id}", response_model=WargameSessionResponse)
async def get_wargame(id: str) -> WargameSessionResponse:
    session = _manager.wargame_suite.engine.get_session(id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return WargameSessionResponse(
        session_id=session.session_id,
        status=session.status,
        current_turn=session.current_turn,
        config=session.config.to_dict(),
        result=session.result.to_dict() if session.result else None,
    )


@training_sim_router.get("/training/wargame/{id}/result", response_model=WargameResultResponse)
async def get_wargame_result(id: str) -> WargameResultResponse:
    session = _manager.wargame_suite.engine.get_session(id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    if session.result is None:
        result = _manager.wargame_suite.engine.complete(id)
    else:
        result = session.result
    return WargameResultResponse(result=result.to_dict())


@training_sim_router.get("/training/wargame/{id}/replay", response_model=ReplayResponse)
async def get_wargame_replay(id: str) -> ReplayResponse:
    try:
        frames = _manager.get_replay(id)
        return ReplayResponse(session_id=id, frames=frames)
    except Exception as exc:
        raise _to_http(exc) from exc


@training_sim_router.get("/training/wargames", response_model=Dict[str, List[dict]])
async def list_wargames() -> Dict[str, List[dict]]:
    sessions = _manager.wargame_suite.engine.get_sessions()
    return {"sessions": [session.to_dict() for session in sessions]}


@training_sim_router.post("/training/exercises", response_model=ExerciseResponse)
async def create_exercise(req: ExerciseCreateRequest) -> ExerciseResponse:
    try:
        ex = _manager.create_exercise(req.name, req.type, req.phases, req.participants)
        return ExerciseResponse(exercise=ex.to_dict())
    except Exception as exc:
        raise _to_http(exc) from exc


@training_sim_router.post("/training/exercises/tabletop", response_model=ExerciseResponse)
async def create_tabletop(body: Dict[str, Any]) -> ExerciseResponse:
    try:
        ex = _manager.create_tabletop(
            body.get("name", "Tabletop Exercise"),
            body.get("brief", "Default tactical brief"),
            body.get("participants", []),
        )
        return ExerciseResponse(exercise=ex.to_dict())
    except Exception as exc:
        raise _to_http(exc) from exc


@training_sim_router.post("/training/exercises/cyber", response_model=ExerciseResponse)
async def create_cyber(body: Dict[str, Any]) -> ExerciseResponse:
    try:
        ex = _manager.exercise_framework.create_cyber_exercise(
            body.get("name", "Cyber Exercise"),
            body.get("participants", []),
            body.get("scenario_type", "brute_force"),
        )
        return ExerciseResponse(exercise=ex.to_dict())
    except Exception as exc:
        raise _to_http(exc) from exc


@training_sim_router.get("/training/exercises", response_model=Dict[str, List[dict]])
async def list_exercises() -> Dict[str, List[dict]]:
    return {"exercises": [exercise.to_dict() for exercise in _manager.exercise_framework.get_exercises()]}


@training_sim_router.get("/training/exercises/{id}", response_model=ExerciseResponse)
async def get_exercise(id: str) -> ExerciseResponse:
    exercise = _manager.exercise_framework.get_exercise(id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="exercise not found")
    return ExerciseResponse(exercise=exercise.to_dict())


@training_sim_router.post("/training/exercises/{id}/evaluate", response_model=ExerciseScoreResponse)
async def evaluate_exercise(id: str) -> ExerciseScoreResponse:
    try:
        score = _manager.evaluate_exercise(id)
        return ExerciseScoreResponse(score=score.to_dict())
    except Exception as exc:
        raise _to_http(exc) from exc


@training_sim_router.post("/training/officers", response_model=OfficerResponse)
async def register_officer(req: RegisterOfficerRequest) -> OfficerResponse:
    officer = _manager.register_officer(req.name, req.rank, req.unit, req.specialization)
    return OfficerResponse(officer=officer.to_dict())


@training_sim_router.get("/training/officers", response_model=Dict[str, List[dict]])
async def list_officers(
    rank: Optional[str] = Query(default=None),
    unit: Optional[str] = Query(default=None),
    specialization: Optional[str] = Query(default=None),
) -> Dict[str, List[dict]]:
    officers = _manager.training_portal.officers.get_officers(rank=rank, unit=unit, specialization=specialization)
    return {"officers": [officer.to_dict() for officer in officers]}


@training_sim_router.get("/training/officers/{id}", response_model=OfficerProfileResponse)
async def get_officer(id: str) -> OfficerProfileResponse:
    try:
        profile = _manager.training_portal.officers.get_officer_profile(id)
        return OfficerProfileResponse(profile=profile)
    except Exception as exc:
        raise _to_http(exc) from exc


@training_sim_router.post("/training/officers/{id}/assign", response_model=AssignmentResponse)
async def assign_to_officer(id: str, req: AssignCourseRequest) -> AssignmentResponse:
    due = None
    if req.due_date:
        due = datetime.fromisoformat(req.due_date)
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
    assignment = _manager.training_portal.assignments.assign(
        officer_id=id,
        course_id=req.course_id,
        exercise_id=req.exercise_id,
        wargame_id=req.wargame_id,
        due_date=due,
    )
    return AssignmentResponse(assignment=assignment.to_dict())


@training_sim_router.get("/training/assignments", response_model=Dict[str, List[dict]])
async def list_assignments(officer_id: Optional[str] = Query(default=None), status: Optional[str] = Query(default=None)) -> Dict[str, List[dict]]:
    rows = _manager.training_portal.assignments.get_assignments(officer_id=officer_id, status=status)
    return {"assignments": [row.to_dict() for row in rows]}


@training_sim_router.get("/training/courses", response_model=Dict[str, List[dict]])
async def list_courses() -> Dict[str, List[dict]]:
    courses = _manager.training_portal.courses.get_courses()
    return {"courses": [course.to_dict() for course in courses]}


@training_sim_router.post("/training/courses/standard", response_model=Dict[str, List[dict]])
async def generate_standard_courses() -> Dict[str, List[dict]]:
    courses = _manager.training_portal.courses.create_standard_courses()
    return {"courses": [course.to_dict() for course in courses]}


@training_sim_router.post("/training/scenarios/from-brief", response_model=ScenarioResponse)
async def scenario_from_brief(req: ScenarioFromBriefRequest) -> ScenarioResponse:
    return ScenarioResponse(scenario=_manager.create_scenario("brief", brief=req.brief))


@training_sim_router.post("/training/scenarios/from-orbat", response_model=ScenarioResponse)
async def scenario_from_orbat(req: ScenarioFromORBATRequest) -> ScenarioResponse:
    scenario = _manager.create_scenario("orbat", blue_force_id=req.blue_id, red_force_id=req.red_id, terrain=req.terrain)
    return ScenarioResponse(scenario=scenario)


@training_sim_router.get("/training/portal/overview", response_model=PortalOverviewResponse)
async def portal_overview() -> PortalOverviewResponse:
    return PortalOverviewResponse(overview=_manager.get_portal_overview())


@training_sim_router.get("/training/readiness/{unit}", response_model=ReadinessResponse)
async def readiness(unit: str) -> ReadinessResponse:
    return ReadinessResponse(readiness=_manager.get_readiness(unit))


@training_sim_router.get("/training/leaderboard", response_model=LeaderboardResponse)
async def leaderboard() -> LeaderboardResponse:
    return LeaderboardResponse(leaderboard=_manager.training_portal.officers.get_leaderboard())


@training_sim_router.post("/training/report", response_model=TrainingReportResponse)
async def training_report() -> TrainingReportResponse:
    return TrainingReportResponse(report=_manager.generate_training_report())


@training_sim_router.get("/training/status", response_model=Dict[str, Any])
async def training_status() -> Dict[str, Any]:
    return _manager.health_check()
