"""Data models for Layer 12 training and simulation workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


WARGAME_TYPES = {"tactical", "operational", "strategic", "cyber", "hybrid"}
ADVERSARY_DIFFICULTY = {"novice", "competent", "expert", "grandmaster"}
SESSION_STATUS = {"setup", "in_progress", "paused", "completed", "aborted"}
EXERCISE_TYPES = {"tabletop", "command_post", "field", "cyber", "combined"}
PHASE_STATUS = {"pending", "active", "completed"}
ASSIGNMENT_STATUS = {"assigned", "in_progress", "completed", "overdue"}


@dataclass
class WargameConfig:
    wargame_id: str
    name: str
    description: str
    wargame_type: str
    scenario_id: Optional[str]
    blue_force_id: str
    red_force_id: str
    turn_limit: int
    turn_duration_seconds: float
    llm_adversary: bool
    adversary_difficulty: str
    rules_of_engagement: str
    victory_conditions: List[dict] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.wargame_type not in WARGAME_TYPES:
            raise ValueError("invalid wargame_type")
        if self.adversary_difficulty not in ADVERSARY_DIFFICULTY:
            raise ValueError("invalid adversary_difficulty")
        if self.turn_limit <= 0:
            raise ValueError("turn_limit must be > 0")
        if self.turn_duration_seconds <= 0:
            raise ValueError("turn_duration_seconds must be > 0")

    def to_dict(self) -> dict:
        return {
            "wargame_id": self.wargame_id,
            "name": self.name,
            "description": self.description,
            "wargame_type": self.wargame_type,
            "scenario_id": self.scenario_id,
            "blue_force_id": self.blue_force_id,
            "red_force_id": self.red_force_id,
            "turn_limit": self.turn_limit,
            "turn_duration_seconds": self.turn_duration_seconds,
            "llm_adversary": self.llm_adversary,
            "adversary_difficulty": self.adversary_difficulty,
            "rules_of_engagement": self.rules_of_engagement,
            "victory_conditions": list(self.victory_conditions),
            "parameters": dict(self.parameters),
        }


@dataclass
class WargameTurn:
    turn_number: int
    timestamp: datetime
    blue_orders: List[dict]
    red_orders: List[dict]
    events: List[dict]
    state_snapshot: dict
    blue_losses: int
    red_losses: int
    llm_reasoning: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "turn_number": self.turn_number,
            "timestamp": self.timestamp.isoformat(),
            "blue_orders": list(self.blue_orders),
            "red_orders": list(self.red_orders),
            "events": list(self.events),
            "state_snapshot": dict(self.state_snapshot),
            "blue_losses": self.blue_losses,
            "red_losses": self.red_losses,
            "llm_reasoning": self.llm_reasoning,
        }


@dataclass
class WargameResult:
    wargame_id: str
    turns_played: int
    duration_seconds: float
    outcome: str
    blue_score: float
    red_score: float
    blue_losses_total: int
    red_losses_total: int
    objectives_met: List[str]
    objectives_failed: List[str]
    key_decisions: List[dict]
    llm_aar: Optional[str]
    lessons_learned: List[str]
    performance_score: float

    def to_dict(self) -> dict:
        return {
            "wargame_id": self.wargame_id,
            "turns_played": self.turns_played,
            "duration_seconds": self.duration_seconds,
            "outcome": self.outcome,
            "blue_score": self.blue_score,
            "red_score": self.red_score,
            "blue_losses_total": self.blue_losses_total,
            "red_losses_total": self.red_losses_total,
            "objectives_met": list(self.objectives_met),
            "objectives_failed": list(self.objectives_failed),
            "key_decisions": list(self.key_decisions),
            "llm_aar": self.llm_aar,
            "lessons_learned": list(self.lessons_learned),
            "performance_score": self.performance_score,
        }

    def summary(self) -> str:
        return (
            f"Wargame {self.wargame_id}: outcome={self.outcome}, turns={self.turns_played}, "
            f"blue_score={self.blue_score:.1f}, red_score={self.red_score:.1f}, "
            f"officer_performance={self.performance_score:.1f}"
        )


@dataclass
class WargameSession:
    session_id: str
    config: WargameConfig
    status: str
    current_turn: int
    turns: List[WargameTurn] = field(default_factory=list)
    result: Optional[WargameResult] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    officer_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in SESSION_STATUS:
            raise ValueError("invalid session status")

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "config": self.config.to_dict(),
            "status": self.status,
            "current_turn": self.current_turn,
            "turns": [turn.to_dict() for turn in self.turns],
            "result": self.result.to_dict() if self.result else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "officer_id": self.officer_id,
        }

    def is_active(self) -> bool:
        return self.status in {"setup", "in_progress", "paused"}


@dataclass
class AdversaryProfile:
    profile_id: str
    name: str
    difficulty: str
    doctrine: str
    personality_traits: List[str]
    preferred_tactics: List[str]
    llm_system_prompt: str

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "difficulty": self.difficulty,
            "doctrine": self.doctrine,
            "personality_traits": list(self.personality_traits),
            "preferred_tactics": list(self.preferred_tactics),
            "llm_system_prompt": self.llm_system_prompt,
        }


@dataclass
class ExercisePhase:
    phase_id: str
    name: str
    description: str
    duration_minutes: int
    objectives: List[str]
    evaluation_criteria: List[str]
    wargame_ids: List[str]
    status: str = "pending"

    def __post_init__(self) -> None:
        if self.status not in PHASE_STATUS:
            raise ValueError("invalid phase status")

    def to_dict(self) -> dict:
        return {
            "phase_id": self.phase_id,
            "name": self.name,
            "description": self.description,
            "duration_minutes": self.duration_minutes,
            "objectives": list(self.objectives),
            "evaluation_criteria": list(self.evaluation_criteria),
            "wargame_ids": list(self.wargame_ids),
            "status": self.status,
        }


@dataclass
class Exercise:
    exercise_id: str
    name: str
    description: str
    exercise_type: str
    phases: List[ExercisePhase]
    participants: List[dict]
    dis_exercise_id: Optional[int]
    c2sim_session: Optional[str]
    status: str
    created_at: datetime
    final_score: Optional[float] = None
    aar: Optional[str] = None

    def __post_init__(self) -> None:
        if self.exercise_type not in EXERCISE_TYPES:
            raise ValueError("invalid exercise_type")

    def to_dict(self) -> dict:
        return {
            "exercise_id": self.exercise_id,
            "name": self.name,
            "description": self.description,
            "exercise_type": self.exercise_type,
            "phases": [phase.to_dict() for phase in self.phases],
            "participants": list(self.participants),
            "dis_exercise_id": self.dis_exercise_id,
            "c2sim_session": self.c2sim_session,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "final_score": self.final_score,
            "aar": self.aar,
        }

    def current_phase(self) -> Optional[ExercisePhase]:
        for phase in self.phases:
            if phase.status in {"active", "pending"}:
                return phase
        return None

    def is_active(self) -> bool:
        return self.status in {"created", "active", "in_progress"}


@dataclass
class ExerciseScore:
    score_id: str
    exercise_id: str
    officer_id: str
    phase_scores: Dict[str, float]
    overall_score: float
    grade: str
    strengths: List[str]
    weaknesses: List[str]
    llm_feedback: Optional[str]
    scored_at: datetime

    def to_dict(self) -> dict:
        return {
            "score_id": self.score_id,
            "exercise_id": self.exercise_id,
            "officer_id": self.officer_id,
            "phase_scores": dict(self.phase_scores),
            "overall_score": self.overall_score,
            "grade": self.grade,
            "strengths": list(self.strengths),
            "weaknesses": list(self.weaknesses),
            "llm_feedback": self.llm_feedback,
            "scored_at": self.scored_at.isoformat(),
        }


@dataclass
class OfficerRecord:
    officer_id: str
    name: str
    rank: str
    unit: str
    specialization: str
    exercises_completed: List[str] = field(default_factory=list)
    wargames_played: List[str] = field(default_factory=list)
    courses_completed: List[str] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    average_score: float = 0.0
    performance_trend: str = "stable"
    strengths: List[str] = field(default_factory=list)
    development_areas: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "officer_id": self.officer_id,
            "name": self.name,
            "rank": self.rank,
            "unit": self.unit,
            "specialization": self.specialization,
            "exercises_completed": list(self.exercises_completed),
            "wargames_played": list(self.wargames_played),
            "courses_completed": list(self.courses_completed),
            "certifications": list(self.certifications),
            "average_score": self.average_score,
            "performance_trend": self.performance_trend,
            "strengths": list(self.strengths),
            "development_areas": list(self.development_areas),
        }

    def readiness_score(self) -> float:
        cert_bonus = min(10.0, len(self.certifications) * 2.0)
        trend_bonus = {"improving": 5.0, "stable": 2.0, "declining": -5.0}.get(self.performance_trend, 0.0)
        return max(0.0, min(100.0, self.average_score + cert_bonus + trend_bonus))


@dataclass
class CourseModule:
    module_id: str
    name: str
    type: str
    duration_minutes: int
    required: bool = True

    def to_dict(self) -> dict:
        return {
            "module_id": self.module_id,
            "name": self.name,
            "type": self.type,
            "duration_minutes": self.duration_minutes,
            "required": self.required,
        }


@dataclass
class Course:
    course_id: str
    name: str
    description: str
    course_type: str
    modules: List[dict]
    prerequisites: List[str] = field(default_factory=list)
    certification_awarded: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "course_id": self.course_id,
            "name": self.name,
            "description": self.description,
            "course_type": self.course_type,
            "modules": list(self.modules),
            "prerequisites": list(self.prerequisites),
            "certification_awarded": self.certification_awarded,
        }

    def total_hours(self) -> float:
        minutes = 0
        for module in self.modules:
            minutes += int(module.get("duration_minutes", 0))
        return round(minutes / 60.0, 2)


@dataclass
class Assignment:
    assignment_id: str
    officer_id: str
    course_id: Optional[str]
    exercise_id: Optional[str]
    wargame_id: Optional[str]
    assigned_at: datetime
    due_date: Optional[datetime]
    status: str
    score: Optional[float] = None

    def __post_init__(self) -> None:
        if self.status not in ASSIGNMENT_STATUS:
            raise ValueError("invalid assignment status")

    def to_dict(self) -> dict:
        return {
            "assignment_id": self.assignment_id,
            "officer_id": self.officer_id,
            "course_id": self.course_id,
            "exercise_id": self.exercise_id,
            "wargame_id": self.wargame_id,
            "assigned_at": self.assigned_at.isoformat(),
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "status": self.status,
            "score": self.score,
        }

    def is_overdue(self) -> bool:
        if self.status == "completed" or self.due_date is None:
            return False
        now = datetime.now(timezone.utc)
        due = self.due_date
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        return now > due
