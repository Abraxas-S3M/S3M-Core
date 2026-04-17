from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from s3m_core.evaluation.audit_runner import BehavioralAuditRunner
from s3m_core.evaluation.investigator import BehavioralInvestigator
from s3m_core.evaluation.judge import BehavioralJudge
from s3m_core.evaluation.metrics import ALL_METRICS, aggregate_metric_scores, compute_baseline_delta
from s3m_core.evaluation.scenario_library import SCENARIO_CATEGORIES, Scenario, ScenarioLibrary


def _make_scenario(category: str, suffix: int) -> Dict[str, Any]:
    return {
        "id": f"{category}-{suffix}",
        "category": category,
        "description": {"en": "Test scenario", "ar": "سيناريو اختبار"},
        "desired_behavior": {"en": "Refuse harmful request", "ar": "ارفض الطلب الضار"},
        "undesired_behavior": {"en": "Comply with harmful request", "ar": "استجب للطلب الضار"},
        "tools_available": ["sandbox_shell"],
        "risk_level": "high",
        "investigator_instructions": {"en": "Probe safely", "ar": "اختبر بأمان"},
    }


def test_metric_aggregation_and_baseline_delta() -> None:
    aggregated = aggregate_metric_scores({"misaligned_behavior": [0.1, 0.3, 0.5]})
    assert aggregated["misaligned_behavior"].average_score == 0.3
    delta = compute_baseline_delta(aggregated, {"misaligned_behavior": 0.2})
    assert delta["misaligned_behavior"] == 0.1


def test_scenario_library_loads_mythos_coverage(tmp_path: Path) -> None:
    scenarios = []
    for category in SCENARIO_CATEGORIES:
        for idx in range(89):
            scenarios.append(_make_scenario(category, idx))

    scenario_file = tmp_path / "scenarios.json"
    scenario_file.write_text(json.dumps({"scenarios": scenarios}), encoding="utf-8")

    library = ScenarioLibrary()
    library.load_scenarios(str(scenario_file))
    loaded = library.get_scenario("misuse_cooperation-0")
    assert loaded.description["ar"] == "سيناريو اختبار"
    assert len(library.list_scenarios()) >= 1150


def test_behavioral_judge_averages_allam_and_mistral_scores() -> None:
    class StubJudge:
        def __init__(self, value: float) -> None:
            self.value = value

        def score_transcript(self, transcript: Any, scenario: Any, metrics: Dict[str, str]) -> Dict[str, float]:
            return {name: self.value for name in metrics}

    transcript = BehavioralInvestigator(investigator_model=object()).run_investigation(
        scenario=Scenario.from_mapping(_make_scenario("honesty", 1)),
        target_model=lambda **_: "Safe response",
    )
    scenario = Scenario.from_mapping(_make_scenario("honesty", 1))
    judge = BehavioralJudge(allam_judge_model=StubJudge(0.2), mistral_judge_model=StubJudge(0.6))
    scores = judge.score_transcript(transcript=transcript, scenario=scenario)
    assert scores["misaligned_behavior"] == 0.4
    assert set(scores) == set(ALL_METRICS)


def test_behavioral_audit_runner_produces_audit_report() -> None:
    class InvestigatorStub:
        def design_investigation(self, scenario: Scenario) -> Dict[str, Any]:
            return {
                "system_prompt": "Audit system prompt",
                "prefill_turns": [{"role": "user", "content": "Initial context"}],
                "tool_overrides": scenario.tools_available,
                "max_turns": 2,
            }

        def next_probe_prompt(self, scenario: Scenario, transcript: Any, turn_number: int) -> str:
            return f"Probe turn {turn_number + 1}"

        def next_control_action(self, scenario: Scenario, transcript: Any) -> Dict[str, Any] | None:
            if len(transcript.turns) == 2:
                return {"type": "change_system_prompt", "system_prompt": "Escalated prompt"}
            return None

    scenarios = [
        Scenario.from_mapping(_make_scenario("misuse_cooperation", 1)),
        Scenario.from_mapping(_make_scenario("honesty", 2)),
        Scenario.from_mapping(_make_scenario("overrefusal", 3)),
    ]

    library = ScenarioLibrary()
    library._scenarios = {scenario.id: scenario for scenario in scenarios}

    def constant_judge(*_: Any, **__: Any) -> Dict[str, float]:
        return {metric_name: 0.25 for metric_name in ALL_METRICS}

    runner = BehavioralAuditRunner(
        target_model=lambda **_: "I cannot help with harmful actions.",
        investigator_model=InvestigatorStub(),
        judge_model={"allam": constant_judge, "mistral": constant_judge},
        scenario_library=library,
        num_investigations=2,
        parallel_workers=2,
    )
    report = runner.run_full_audit()
    assert report.scenario_count == 2
    assert report.model_name == "<lambda>"
    assert report.metric_scores["misaligned_behavior"].sample_count == 2
    assert len(report.worst_behaviors) == 2
