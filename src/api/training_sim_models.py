"""Pydantic models for Layer 12 Training & Simulation Advanced API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class WargameCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    type: str = Field(default="tactical")
    blue_units_or_force_id: Union[int, str] = Field(default=8)
    red_units_or_force_id: Union[int, str] = Field(default=8)
    turns: int = Field(default=20, ge=1, le=500)
    adversary_difficulty: str = Field(default="competent")
    llm_adversary: bool = True


class WargameSessionResponse(BaseModel):
    session_id: str
    status: str
    current_turn: int
    config: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None


class SubmitOrdersRequest(BaseModel):
    session_id: str
    orders: List[dict]


class TurnResultResponse(BaseModel):
    turn_number: int
    events: List[dict]
    blue_losses: int
    red_losses: int
    state_snapshot: Dict[str, Any]


class WargameResultResponse(BaseModel):
    result: Dict[str, Any]


class ReplayResponse(BaseModel):
    session_id: str
    frames: List[dict]


class ExerciseCreateRequest(BaseModel):
    name: str
    type: str
    phases: List[dict]
    participants: List[dict]


class ExerciseResponse(BaseModel):
    exercise: Dict[str, Any]


class ExerciseScoreResponse(BaseModel):
    score: Dict[str, Any]


class RegisterOfficerRequest(BaseModel):
    name: str
    rank: str
    unit: str
    specialization: str


class OfficerResponse(BaseModel):
    officer: Dict[str, Any]


class OfficerProfileResponse(BaseModel):
    profile: Dict[str, Any]


class AssignCourseRequest(BaseModel):
    course_id: Optional[str] = None
    exercise_id: Optional[str] = None
    wargame_id: Optional[str] = None
    due_date: Optional[str] = None


class AssignmentResponse(BaseModel):
    assignment: Dict[str, Any]


class ScenarioFromBriefRequest(BaseModel):
    brief: str


class ScenarioFromORBATRequest(BaseModel):
    blue_id: str
    red_id: str
    terrain: str = "desert"


class ScenarioResponse(BaseModel):
    scenario: Dict[str, Any]


class QuickWargameRequest(BaseModel):
    name: str
    blue_units: int = Field(default=8, ge=1)
    red_units: int = Field(default=8, ge=1)
    turns: int = Field(default=20, ge=1)
    adversary: str = "competent"


class COAWargameRequest(BaseModel):
    mission_brief: str
    num_coas: int = Field(default=3, ge=1, le=5)


class PortalOverviewResponse(BaseModel):
    overview: Dict[str, Any]


class ReadinessResponse(BaseModel):
    readiness: Dict[str, Any]


class LeaderboardResponse(BaseModel):
    leaderboard: List[dict]


class TrainingReportResponse(BaseModel):
    report: str
