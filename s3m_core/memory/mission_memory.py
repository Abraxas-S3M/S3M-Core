"""Persistent long-horizon mission memory for S3M operations.

Military/tactical context:
Persistent mission memory preserves command intent, execution outcomes, and
lessons learned across multi-day operations so future planning cycles can
avoid repeated tactical mistakes and reinforce successful patterns.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import math
import re

_MISSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(parsed):
        return float(default)
    return parsed


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return int(default)
    return parsed


@dataclass
class EmotionProfile:
    """Operator and model-affect profile captured per mission step."""

    stress: float = 0.0
    confidence: float = 0.0
    focus: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stress": _safe_float(self.stress),
            "confidence": _safe_float(self.confidence),
            "focus": _safe_float(self.focus),
            "notes": [str(note) for note in self.notes],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "EmotionProfile":
        data = payload or {}
        notes_raw = data.get("notes", [])
        notes = [str(item) for item in notes_raw] if isinstance(notes_raw, list) else []
        return cls(
            stress=_safe_float(data.get("stress", 0.0)),
            confidence=_safe_float(data.get("confidence", 0.0)),
            focus=_safe_float(data.get("focus", 0.0)),
            notes=notes,
        )


@dataclass
class MissionStep:
    """Single execution record within a tactical mission timeline."""

    step_id: str
    description: str
    action_taken: str
    result: str
    success: bool
    duration_seconds: float
    tokens_used: int
    sae_alerts: list[Any] = field(default_factory=list)
    emotion_profile: EmotionProfile = field(default_factory=EmotionProfile)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": str(self.step_id),
            "description": str(self.description),
            "action_taken": str(self.action_taken),
            "result": str(self.result),
            "success": bool(self.success),
            "duration_seconds": _safe_float(self.duration_seconds),
            "tokens_used": _safe_int(self.tokens_used),
            "sae_alerts": list(self.sae_alerts),
            "emotion_profile": self.emotion_profile.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MissionStep":
        if not isinstance(payload, dict):
            raise ValueError("MissionStep payload must be a dictionary")
        return cls(
            step_id=str(payload.get("step_id", "")),
            description=str(payload.get("description", "")),
            action_taken=str(payload.get("action_taken", "")),
            result=str(payload.get("result", "")),
            success=bool(payload.get("success", False)),
            duration_seconds=_safe_float(payload.get("duration_seconds", 0.0)),
            tokens_used=_safe_int(payload.get("tokens_used", 0)),
            sae_alerts=list(payload.get("sae_alerts", [])),
            emotion_profile=EmotionProfile.from_dict(payload.get("emotion_profile", {})),
        )


@dataclass
class TaskPlan:
    """Rolling mission plan used by the commander loop."""

    summary: str = ""
    next_actions: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)
    updated_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": str(self.summary),
            "next_actions": [str(item) for item in self.next_actions],
            "risk_notes": [str(item) for item in self.risk_notes],
            "updated_at": str(self.updated_at),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "TaskPlan":
        data = payload or {}
        next_actions_raw = data.get("next_actions", [])
        risk_notes_raw = data.get("risk_notes", [])
        return cls(
            summary=str(data.get("summary", "")),
            next_actions=[str(item) for item in next_actions_raw] if isinstance(next_actions_raw, list) else [],
            risk_notes=[str(item) for item in risk_notes_raw] if isinstance(risk_notes_raw, list) else [],
            updated_at=str(data.get("updated_at", _utc_now_iso())),
        )


@dataclass
class Mission:
    """Persisted mission state for multi-session operations."""

    mission_id: str
    objective: str
    constraints: list[str]
    status: str
    created_at: str
    steps: list[MissionStep] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    lessons_learned: list[str] = field(default_factory=list)
    current_plan: TaskPlan = field(default_factory=TaskPlan)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": str(self.mission_id),
            "objective": str(self.objective),
            "constraints": [str(item) for item in self.constraints],
            "status": str(self.status),
            "created_at": str(self.created_at),
            "steps": [step.to_dict() for step in self.steps],
            "artifacts": [str(item) for item in self.artifacts],
            "lessons_learned": [str(item) for item in self.lessons_learned],
            "current_plan": self.current_plan.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Mission":
        if not isinstance(payload, dict):
            raise ValueError("Mission payload must be a dictionary")
        steps_raw = payload.get("steps", [])
        return cls(
            mission_id=str(payload.get("mission_id", "")),
            objective=str(payload.get("objective", "")),
            constraints=[str(item) for item in payload.get("constraints", [])],
            status=str(payload.get("status", "created")),
            created_at=str(payload.get("created_at", _utc_now_iso())),
            steps=[MissionStep.from_dict(item) for item in steps_raw] if isinstance(steps_raw, list) else [],
            artifacts=[str(item) for item in payload.get("artifacts", [])],
            lessons_learned=[str(item) for item in payload.get("lessons_learned", [])],
            current_plan=TaskPlan.from_dict(payload.get("current_plan", {})),
        )


class MissionMemory:
    """Persistent state store for long-running missions."""

    def __init__(self, storage_path: str = "./s3m_missions/") -> None:
        path = str(storage_path).strip()
        if not path:
            raise ValueError("storage_path must be a non-empty string")
        self.storage_path = Path(path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def create_mission(self, mission_id: str, objective: str, constraints: list[str]) -> Mission:
        """Create and persist a mission record."""

        clean_id = self._validate_mission_id(mission_id)
        clean_objective = self._validate_text(objective, field_name="objective")
        clean_constraints = self._validate_string_list(constraints, field_name="constraints")
        mission_path = self._mission_path(clean_id)
        if mission_path.exists():
            raise ValueError(f"mission_id '{clean_id}' already exists")

        mission = Mission(
            mission_id=clean_id,
            objective=clean_objective,
            constraints=clean_constraints,
            status="created",
            created_at=_utc_now_iso(),
            steps=[],
            artifacts=[],
            lessons_learned=[],
            current_plan=TaskPlan(summary="Mission initialized."),
        )
        self._save_mission(mission)
        return mission

    def save_step(self, mission_id: str, step: MissionStep) -> None:
        """Append a mission step to persistent memory."""

        clean_id = self._validate_mission_id(mission_id)
        if not isinstance(step, MissionStep):
            raise TypeError("step must be a MissionStep instance")

        mission = self._load_mission(clean_id)
        mission.steps.append(step)
        if mission.status in {"created", "in_progress"}:
            mission.status = "in_progress"
        mission.current_plan.updated_at = _utc_now_iso()
        self._save_mission(mission)

    def get_mission_context(self, mission_id: str, max_tokens: int = 50000) -> str:
        """Return a recursively summarized mission context within token budget."""

        clean_id = self._validate_mission_id(mission_id)
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")

        mission = self._load_mission(clean_id)
        chunks = self._build_context_chunks(mission)
        return self._recursive_summarize(chunks, max_tokens=max_tokens)

    def add_lesson(self, mission_id: str, lesson: str) -> None:
        """Record lessons learned for future mission planning."""

        clean_id = self._validate_mission_id(mission_id)
        clean_lesson = self._validate_text(lesson, field_name="lesson")

        mission = self._load_mission(clean_id)
        mission.lessons_learned.append(clean_lesson)
        self._save_mission(mission)

    def get_relevant_lessons(self, new_objective: str, top_k: int = 5) -> list[str]:
        """Return semantically relevant lessons from prior missions."""

        clean_objective = self._validate_text(new_objective, field_name="new_objective")
        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")

        records = self._load_lesson_records()
        if not records:
            return []

        query_terms = self._tokenize(clean_objective)
        scored: list[tuple[float, str]] = []
        for record in records:
            corpus = f"{record['objective']} {record['lesson']}"
            similarity = self._cosine_similarity(query_terms, self._tokenize(corpus))
            if similarity <= 0.0:
                continue
            scored.append((similarity, record["lesson"]))

        if not scored:
            scored = [(0.0001, record["lesson"]) for record in records]

        scored.sort(key=lambda item: item[0], reverse=True)
        ordered_lessons: list[str] = []
        seen: set[str] = set()
        for _, lesson in scored:
            if lesson in seen:
                continue
            seen.add(lesson)
            ordered_lessons.append(lesson)
            if len(ordered_lessons) >= top_k:
                break
        return ordered_lessons

    def _mission_path(self, mission_id: str) -> Path:
        return self.storage_path / f"{mission_id}.json"

    def _save_mission(self, mission: Mission) -> None:
        payload = mission.to_dict()
        self._mission_path(mission.mission_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_mission(self, mission_id: str) -> Mission:
        path = self._mission_path(mission_id)
        if not path.exists():
            raise KeyError(f"mission_id '{mission_id}' does not exist")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return Mission.from_dict(payload)

    def _build_context_chunks(self, mission: Mission) -> list[str]:
        header = [
            "MISSION HEADER",
            f"Mission ID: {mission.mission_id}",
            f"Objective: {mission.objective}",
            f"Status: {mission.status}",
            f"Created At: {mission.created_at}",
            f"Constraints: {'; '.join(mission.constraints) if mission.constraints else 'None'}",
            f"Current Plan Summary: {mission.current_plan.summary or 'Not set'}",
            f"Current Plan Next Actions: {', '.join(mission.current_plan.next_actions) if mission.current_plan.next_actions else 'None'}",
            f"Current Plan Risk Notes: {', '.join(mission.current_plan.risk_notes) if mission.current_plan.risk_notes else 'None'}",
        ]
        chunks: list[str] = ["\n".join(header)]

        for step in mission.steps:
            # Tactical context: step summaries preserve why choices were made,
            # so future planning can avoid repeating unsafe maneuvers.
            chunks.append(
                "\n".join(
                    [
                        f"STEP {step.step_id}",
                        f"Description: {step.description}",
                        f"Action Taken: {step.action_taken}",
                        f"Result: {step.result}",
                        f"Success: {step.success}",
                        f"Duration Seconds: {step.duration_seconds}",
                        f"Tokens Used: {step.tokens_used}",
                        f"SAE Alerts: {step.sae_alerts if step.sae_alerts else 'None'}",
                        f"Emotion Profile: stress={step.emotion_profile.stress}, confidence={step.emotion_profile.confidence}, focus={step.emotion_profile.focus}",
                    ]
                )
            )

        if mission.artifacts:
            chunks.append("ARTIFACTS\n" + "\n".join(f"- {artifact}" for artifact in mission.artifacts))
        if mission.lessons_learned:
            chunks.append("LESSONS LEARNED\n" + "\n".join(f"- {lesson}" for lesson in mission.lessons_learned))
        return chunks

    def _recursive_summarize(self, chunks: list[str], *, max_tokens: int) -> str:
        if not chunks:
            return ""
        combined = "\n\n".join(chunks)
        if self._estimate_tokens(combined) <= max_tokens:
            return combined
        if len(chunks) == 1:
            return self._truncate_to_tokens(chunks[0], max_tokens)

        grouped: list[str] = []
        group_size = 3
        target_per_group = max(64, max_tokens // max(1, math.ceil(len(chunks) / group_size)))
        for index in range(0, len(chunks), group_size):
            grouped.append(self._summarize_chunk(chunks[index : index + group_size], token_budget=target_per_group))
        return self._recursive_summarize(grouped, max_tokens=max_tokens)

    def _summarize_chunk(self, chunks: list[str], *, token_budget: int) -> str:
        lines: list[str] = []
        for chunk in chunks:
            chunk_lines = [line.strip() for line in chunk.splitlines() if line.strip()]
            if not chunk_lines:
                continue
            lines.append(chunk_lines[0])
            if len(chunk_lines) > 1:
                lines.append(chunk_lines[-1])
        summary = "\n".join(lines)
        return self._truncate_to_tokens(summary, token_budget)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, math.ceil(len(text.split()) * 1.25))

    @staticmethod
    def _truncate_to_tokens(text: str, max_tokens: int) -> str:
        words = text.split()
        if len(words) <= max_tokens:
            return text
        return " ".join(words[:max_tokens])

    def _load_lesson_records(self) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for candidate in sorted(self.storage_path.glob("*.json")):
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            objective = str(payload.get("objective", ""))
            lessons = payload.get("lessons_learned", [])
            if not objective or not isinstance(lessons, list):
                continue
            for lesson in lessons:
                lesson_text = str(lesson).strip()
                if lesson_text:
                    records.append({"objective": objective, "lesson": lesson_text})
        return records

    @staticmethod
    def _tokenize(text: str) -> Counter[str]:
        tokens = _TOKEN_PATTERN.findall(text.lower())
        filtered = [token for token in tokens if len(token) > 2]
        return Counter(filtered)

    @staticmethod
    def _cosine_similarity(left: Counter[str], right: Counter[str]) -> float:
        if not left or not right:
            return 0.0
        overlap = set(left).intersection(right)
        numerator = sum(left[token] * right[token] for token in overlap)
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return numerator / (left_norm * right_norm)

    @staticmethod
    def _validate_mission_id(mission_id: str) -> str:
        candidate = str(mission_id).strip()
        if not candidate:
            raise ValueError("mission_id must be non-empty")
        if not _MISSION_ID_PATTERN.match(candidate):
            raise ValueError("mission_id must match [A-Za-z0-9._-]+")
        return candidate

    @staticmethod
    def _validate_text(value: str, *, field_name: str) -> str:
        candidate = str(value).strip()
        if not candidate:
            raise ValueError(f"{field_name} must be non-empty")
        if len(candidate) > 10000:
            raise ValueError(f"{field_name} is too long")
        return candidate

    @staticmethod
    def _validate_string_list(values: list[str], *, field_name: str) -> list[str]:
        if not isinstance(values, list):
            raise ValueError(f"{field_name} must be a list of strings")
        cleaned: list[str] = []
        for item in values:
            text = str(item).strip()
            if text:
                cleaned.append(text)
        return cleaned
