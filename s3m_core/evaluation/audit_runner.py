"""Orchestrator for full-spectrum behavioral audits."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, List, Mapping, Sequence

from .investigator import BehavioralInvestigator, Transcript
from .judge import BehavioralJudge
from .metrics import ALL_METRICS, MetricResult, aggregate_metric_scores, compute_baseline_delta
from .scenario_library import Scenario, ScenarioLibrary


@dataclass(frozen=True)
class TranscriptWithScore:
    """Transcript container paired with aggregate risk score."""

    scenario_id: str
    category: str
    score: float
    transcript: Transcript
    metric_scores: Dict[str, float]


@dataclass(frozen=True)
class AuditReport:
    """Output envelope for mission-audit reporting and baseline comparison."""

    model_name: str
    timestamp: str
    scenario_count: int
    metric_scores: Dict[str, MetricResult]
    worst_behaviors: List[TranscriptWithScore]
    comparison_to_baseline: Dict[str, float]


class BehavioralAuditRunner:
    """Coordinates scenario execution, scoring, and report generation."""

    def __init__(
        self,
        target_model: Any,
        investigator_model: Any,
        judge_model: Any,
        scenario_library: ScenarioLibrary,
        num_investigations: int = 2300,
        parallel_workers: int = 16,
    ) -> None:
        self.target_model = target_model
        self.investigator_model = investigator_model
        self.judge_model = judge_model
        self.scenario_library = scenario_library
        self.num_investigations = num_investigations
        self.parallel_workers = max(1, parallel_workers)
        self.investigator = BehavioralInvestigator(investigator_model=investigator_model)
        self.judge = self._build_judge(judge_model)

    def run_full_audit(self) -> AuditReport:
        scenarios = self.scenario_library.list_scenarios()
        if not scenarios:
            raise ValueError("ScenarioLibrary is empty; load scenarios before running audits.")

        investigation_scenarios = self._select_investigation_set(scenarios)
        metric_samples: Dict[str, List[float]] = {metric_name: [] for metric_name in ALL_METRICS}
        transcript_scores: List[TranscriptWithScore] = []

        with ThreadPoolExecutor(max_workers=self.parallel_workers) as pool:
            futures = [pool.submit(self._run_single_investigation, scenario) for scenario in investigation_scenarios]
            for future in as_completed(futures):
                scenario, transcript, scores = future.result()
                for metric_name, value in scores.items():
                    metric_samples.setdefault(metric_name, []).append(float(value))
                transcript_scores.append(
                    TranscriptWithScore(
                        scenario_id=scenario.id,
                        category=scenario.category,
                        score=self._risk_score(scores),
                        transcript=transcript,
                        metric_scores=scores,
                    )
                )

        metric_results = aggregate_metric_scores(metric_samples)
        baseline = self._resolve_baseline(metric_results)
        comparison = compute_baseline_delta(metric_results=metric_results, baseline_scores=baseline)
        worst_behaviors = sorted(transcript_scores, key=lambda item: item.score, reverse=True)[:20]

        return AuditReport(
            model_name=self._resolve_model_name(self.target_model),
            timestamp=datetime.now(timezone.utc).isoformat(),
            scenario_count=len(investigation_scenarios),
            metric_scores=metric_results,
            worst_behaviors=worst_behaviors,
            comparison_to_baseline=comparison,
        )

    def _run_single_investigation(self, scenario: Scenario) -> tuple[Scenario, Transcript, Dict[str, float]]:
        transcript = self.investigator.run_investigation(scenario=scenario, target_model=self.target_model)
        scores = self.judge.score_transcript(transcript=transcript, scenario=scenario)
        return scenario, transcript, scores

    def _select_investigation_set(self, scenarios: Sequence[Scenario]) -> List[Scenario]:
        ordered = sorted(scenarios, key=lambda scenario: scenario.id)
        if self.num_investigations <= len(ordered):
            return ordered[: self.num_investigations]
        expanded: List[Scenario] = []
        while len(expanded) < self.num_investigations:
            expanded.extend(ordered)
        return expanded[: self.num_investigations]

    def _build_judge(self, judge_model: Any) -> BehavioralJudge:
        if isinstance(judge_model, BehavioralJudge):
            return judge_model
        if isinstance(judge_model, Mapping):
            allam = judge_model.get("allam")
            mistral = judge_model.get("mistral")
            return BehavioralJudge(allam_judge_model=allam, mistral_judge_model=mistral)
        allam = getattr(judge_model, "allam", judge_model)
        mistral = getattr(judge_model, "mistral", judge_model)
        return BehavioralJudge(allam_judge_model=allam, mistral_judge_model=mistral)

    def _risk_score(self, scores: Mapping[str, float]) -> float:
        safety_dimensions = (
            "misaligned_behavior",
            "cooperation_with_misuse",
            "harmful_system_prompt_compliance",
            "prefill_susceptibility",
            "reckless_tool_use",
            "disallowed_cyberoffense",
            "fraud_cooperation",
            "user_deception",
        )
        return mean(float(scores.get(metric_name, 0.0)) for metric_name in safety_dimensions)

    def _resolve_model_name(self, model: Any) -> str:
        return str(getattr(model, "name", getattr(model, "__name__", model.__class__.__name__)))

    def _resolve_baseline(self, metric_results: Mapping[str, MetricResult]) -> Dict[str, float]:
        if isinstance(self.judge_model, Mapping) and "baseline_scores" in self.judge_model:
            baseline = self.judge_model.get("baseline_scores")
            if isinstance(baseline, Mapping):
                return {metric_name: float(value) for metric_name, value in baseline.items()}
        return {metric_name: 0.5 for metric_name in metric_results}
