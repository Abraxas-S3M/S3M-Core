"""Mission uplift scoring for tactical human-machine teaming assessments.

Military/tactical context:
The scorer quantifies how much the S3M assistant improves mission execution
relative to human-only operation, with emphasis on autonomous task handling
and outcome quality under operational pressure.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Protocol, Sequence, runtime_checkable


@runtime_checkable
class Mission(Protocol):
    """Protocol used for mission scoring payloads.

    Implementations may be plain objects or dictionaries that expose mission
    telemetry and outcome metrics.
    """

    mission_id: str


@dataclass(frozen=True)
class UpliftReport:
    """Per-mission uplift assessment produced by :class:`UpliftScorer`."""

    score: float
    category: str
    time_saved_estimate: float
    quality_delta: float
    tasks_completed_autonomously: int
    tasks_requiring_human: int
    novel_solutions: int


@dataclass(frozen=True)
class RegressionReport:
    """Version-to-version comparison result for uplift metrics."""

    improved: List[str]
    regressed: List[str]
    unchanged: List[str]
    overall_delta: float


class UpliftScorer:
    """Measure mission uplift delivered by S3M against human baselines."""

    _CATEGORY_BY_LEVEL: Dict[int, str] = {
        0: "no improvement",
        1: "basic assistance",
        2: "expert-level support",
        3: "autonomous execution",
        4: "strategic superiority",
    }

    def __init__(self) -> None:
        self._history: List[Dict[str, Any]] = []

    def score_mission(self, mission: Mission, human_baseline: float = None) -> UpliftReport:
        """Score one mission on the 0-4 tactical uplift scale."""

        baseline_value = self._validate_optional_number(human_baseline, "human_baseline")
        total_tasks = self._read_int(mission, ["total_tasks", "task_count", "tasks_total"], default=0)
        autonomous_tasks = self._read_int(
            mission,
            [
                "tasks_completed_autonomously",
                "autonomous_tasks",
                "completed_autonomous_tasks",
            ],
            default=0,
        )
        human_tasks = self._read_int(
            mission,
            ["tasks_requiring_human", "manual_tasks", "human_tasks"],
            default=max(0, total_tasks - autonomous_tasks),
        )

        if total_tasks <= 0:
            total_tasks = autonomous_tasks + human_tasks
        if autonomous_tasks + human_tasks > total_tasks:
            total_tasks = autonomous_tasks + human_tasks

        novel_solutions = self._read_int(
            mission,
            ["novel_solutions", "novel_solution_count", "innovative_actions"],
            default=0,
        )
        human_time = self._read_optional_float(
            mission,
            ["human_time_minutes", "baseline_time_minutes", "human_elapsed_minutes"],
        )
        s3m_time = self._read_optional_float(
            mission,
            ["s3m_time_minutes", "model_time_minutes", "automated_elapsed_minutes"],
        )
        model_quality = self._read_optional_float(
            mission,
            ["s3m_quality", "model_quality", "quality_score", "mission_quality"],
        )
        baseline_quality = baseline_value
        if baseline_quality is None:
            baseline_quality = self._read_optional_float(
                mission,
                ["human_quality", "baseline_quality", "human_score"],
            )
        if model_quality is None:
            model_quality = baseline_quality if baseline_quality is not None else 0.0
        if baseline_quality is None:
            baseline_quality = 0.0

        time_saved = 0.0
        if human_time is not None and s3m_time is not None:
            time_saved = max(0.0, human_time - s3m_time)
        quality_delta = float(model_quality - baseline_quality)

        autonomy_ratio = float(autonomous_tasks) / float(max(1, total_tasks))
        time_savings_ratio = 0.0 if not human_time or human_time <= 0.0 else time_saved / human_time
        normalized_quality_delta = max(-1.0, min(1.0, quality_delta))
        novelty_factor = min(1.0, float(max(0, novel_solutions)) / 3.0)

        # Tactical weighting favors mission quality and autonomy over pure speed.
        raw_score = (
            1.8 * max(0.0, normalized_quality_delta)
            + 1.6 * autonomy_ratio
            + 0.4 * min(1.0, time_savings_ratio)
            + 0.2 * novelty_factor
        )
        if normalized_quality_delta <= 0.0 and autonomy_ratio < 0.2 and time_saved <= 0.0:
            raw_score = 0.0
        score = max(0.0, min(4.0, raw_score))
        level = self._score_to_level(score)
        category = self._CATEGORY_BY_LEVEL[level]

        report = UpliftReport(
            score=round(score, 3),
            category=category,
            time_saved_estimate=round(time_saved, 3),
            quality_delta=round(quality_delta, 3),
            tasks_completed_autonomously=max(0, int(autonomous_tasks)),
            tasks_requiring_human=max(0, int(human_tasks)),
            novel_solutions=max(0, int(novel_solutions)),
        )
        self._record_history(mission, report)
        return report

    def compare_versions(
        self,
        model_a_scores: List[UpliftReport],
        model_b_scores: List[UpliftReport],
    ) -> RegressionReport:
        """Compare model versions and report metric regressions/improvements."""

        baseline = self._aggregate_reports(model_a_scores)
        candidate = self._aggregate_reports(model_b_scores)
        metric_directions = {
            "score": 1.0,
            "time_saved_estimate": 1.0,
            "quality_delta": 1.0,
            "tasks_completed_autonomously": 1.0,
            "tasks_requiring_human": -1.0,
            "novel_solutions": 1.0,
        }

        improved: List[str] = []
        regressed: List[str] = []
        unchanged: List[str] = []
        signed_deltas: List[float] = []

        for metric_name, direction in metric_directions.items():
            old_value = baseline[metric_name]
            new_value = candidate[metric_name]
            effective_delta = direction * (new_value - old_value)
            normalized = self._normalize_delta(old_value, effective_delta)
            signed_deltas.append(normalized)
            if normalized > 1e-6:
                improved.append(metric_name)
            elif normalized < -1e-6:
                regressed.append(metric_name)
            else:
                unchanged.append(metric_name)

        overall_delta = 0.0 if not signed_deltas else sum(signed_deltas) / len(signed_deltas)
        return RegressionReport(
            improved=improved,
            regressed=regressed,
            unchanged=unchanged,
            overall_delta=round(overall_delta, 6),
        )

    def generate_dashboard_data(self) -> Dict[str, Any]:
        """Build visualization payloads for uplift over time and versions."""

        timeline = [
            {
                "timestamp": item["timestamp"],
                "mission_id": item["mission_id"],
                "model_version": item["model_version"],
                "score": item["report"]["score"],
                "category": item["report"]["category"],
                "quality_delta": item["report"]["quality_delta"],
            }
            for item in self._history
        ]

        by_category: Dict[str, Dict[str, float]] = {}
        by_model_version: Dict[str, Dict[str, float]] = {}
        for item in self._history:
            report = item["report"]
            category = str(report["category"])
            version = str(item["model_version"])
            category_entry = by_category.setdefault(
                category,
                {"missions": 0.0, "average_score": 0.0, "average_quality_delta": 0.0},
            )
            category_entry["missions"] += 1.0
            category_entry["average_score"] += float(report["score"])
            category_entry["average_quality_delta"] += float(report["quality_delta"])

            version_entry = by_model_version.setdefault(
                version,
                {
                    "missions": 0.0,
                    "average_score": 0.0,
                    "average_time_saved_estimate": 0.0,
                    "average_quality_delta": 0.0,
                },
            )
            version_entry["missions"] += 1.0
            version_entry["average_score"] += float(report["score"])
            version_entry["average_time_saved_estimate"] += float(report["time_saved_estimate"])
            version_entry["average_quality_delta"] += float(report["quality_delta"])

        for entry in by_category.values():
            missions = max(1.0, entry["missions"])
            entry["average_score"] = round(entry["average_score"] / missions, 6)
            entry["average_quality_delta"] = round(entry["average_quality_delta"] / missions, 6)
            entry["missions"] = int(entry["missions"])
        for entry in by_model_version.values():
            missions = max(1.0, entry["missions"])
            entry["average_score"] = round(entry["average_score"] / missions, 6)
            entry["average_time_saved_estimate"] = round(
                entry["average_time_saved_estimate"] / missions,
                6,
            )
            entry["average_quality_delta"] = round(entry["average_quality_delta"] / missions, 6)
            entry["missions"] = int(entry["missions"])

        return {
            "uplift_over_time": timeline,
            "by_category": by_category,
            "by_model_version": by_model_version,
        }

    def _record_history(self, mission: Mission, report: UpliftReport) -> None:
        mission_id = self._read_str(mission, ["mission_id", "id", "name"], default="unknown_mission")
        model_version = self._read_str(mission, ["model_version", "version"], default="unknown_version")
        timestamp = self._read_timestamp(mission)
        self._history.append(
            {
                "timestamp": timestamp,
                "mission_id": mission_id,
                "model_version": model_version,
                "report": asdict(report),
            }
        )

    def _aggregate_reports(self, reports: Sequence[UpliftReport]) -> Dict[str, float]:
        if not reports:
            return {
                "score": 0.0,
                "time_saved_estimate": 0.0,
                "quality_delta": 0.0,
                "tasks_completed_autonomously": 0.0,
                "tasks_requiring_human": 0.0,
                "novel_solutions": 0.0,
            }
        count = float(len(reports))
        return {
            "score": sum(float(item.score) for item in reports) / count,
            "time_saved_estimate": sum(float(item.time_saved_estimate) for item in reports) / count,
            "quality_delta": sum(float(item.quality_delta) for item in reports) / count,
            "tasks_completed_autonomously": (
                sum(float(item.tasks_completed_autonomously) for item in reports) / count
            ),
            "tasks_requiring_human": (
                sum(float(item.tasks_requiring_human) for item in reports) / count
            ),
            "novel_solutions": sum(float(item.novel_solutions) for item in reports) / count,
        }

    def _score_to_level(self, score: float) -> int:
        if score < 0.75:
            return 0
        if score < 1.75:
            return 1
        if score < 2.75:
            return 2
        if score < 3.5:
            return 3
        return 4

    def _normalize_delta(self, baseline: float, delta: float) -> float:
        if math.isclose(baseline, 0.0, abs_tol=1e-9):
            return float(delta)
        return float(delta) / abs(float(baseline))

    def _validate_optional_number(self, value: float | None, field_name: str) -> float | None:
        if value is None:
            return None
        if not isinstance(value, (int, float)):
            raise ValueError(f"{field_name} must be numeric when provided")
        numeric = float(value)
        if not math.isfinite(numeric):
            raise ValueError(f"{field_name} must be finite when provided")
        return numeric

    def _read_timestamp(self, mission: Mission) -> str:
        raw = self._read_value(mission, ["timestamp", "completed_at", "ended_at"])
        if raw is None:
            return datetime.now(timezone.utc).isoformat()
        if isinstance(raw, datetime):
            value = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat()
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return datetime.now(timezone.utc).isoformat()

    def _read_optional_float(self, mission: Mission, keys: Sequence[str]) -> float | None:
        raw = self._read_value(mission, keys)
        if raw is None:
            return None
        if not isinstance(raw, (int, float)):
            raise ValueError(f"{keys[0]} must be numeric when provided")
        numeric = float(raw)
        if not math.isfinite(numeric):
            raise ValueError(f"{keys[0]} must be finite")
        return numeric

    def _read_int(self, mission: Mission, keys: Sequence[str], default: int = 0) -> int:
        raw = self._read_value(mission, keys)
        if raw is None:
            return int(default)
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"{keys[0]} must be numeric")
        numeric = int(raw)
        if numeric < 0:
            raise ValueError(f"{keys[0]} cannot be negative")
        return numeric

    def _read_str(self, mission: Mission, keys: Sequence[str], default: str = "") -> str:
        raw = self._read_value(mission, keys)
        if raw is None:
            return default
        if not isinstance(raw, str):
            return default
        return raw.strip() or default

    def _read_value(self, mission: Mission, keys: Sequence[str]) -> Any:
        for key in keys:
            if isinstance(mission, dict) and key in mission:
                return mission[key]
            if hasattr(mission, key):
                return getattr(mission, key)
        return None
