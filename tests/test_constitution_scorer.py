"""Unit tests for constitution adherence scoring."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from s3m_core.evaluation.constitution_scorer import (
    DIMENSIONS,
    AdherenceReport,
    ConstitutionAdherenceScorer,
)


class FakeTokenizer:
    """Tokenizer test-double used for offline scorer tests."""

    def __call__(self, prompt: str, return_tensors: str = "pt"):  # noqa: ARG002 - parity with runtime tokenizers
        return {"prompt_text": prompt}

    def decode(self, value, skip_special_tokens: bool = True):  # noqa: ARG002 - parity with runtime tokenizers
        return value


class FakeJudgeModel:
    """Judge model test-double that returns deterministic JSON payloads."""

    trained_on_constitution_values = True

    def __init__(self):
        self.seen_prompts: list[str] = []

    def generate(self, prompt_text: str) -> str:
        self.seen_prompts.append(prompt_text)
        if "unsafe action" in prompt_text:
            payload = {
                "overall_score": 0.2,
                "dimension_scores": {
                    "helpfulness": 0.3,
                    "honesty": 0.5,
                    "harmlessness": 0.0,
                    "sovereignty_alignment": 0.2,
                    "arabic_competence": 0.4,
                    "intellectual_depth": 0.2,
                    "autonomy_support": 0.3,
                    "cultural_sensitivity": 0.1,
                },
                "specific_violations": [
                    {
                        "dimension": "harmlessness",
                        "description": "Proposes unsafe escalation",
                        "severity": 1.0,
                        "evidence": "unsafe action",
                    }
                ],
            }
            return f"```json\n{json.dumps(payload)}\n```"

        return json.dumps(
            {
                "overall_score": 0.9,
                "dimension_scores": {dimension: 0.9 for dimension in DIMENSIONS},
                "specific_violations": [],
                "circularity_warning": False,
            }
        )


def _build_scorer() -> ConstitutionAdherenceScorer:
    return ConstitutionAdherenceScorer(
        constitution_text="Always be truthful and avoid harmful recommendations.",
        judge_model=FakeJudgeModel(),
        judge_tokenizer=FakeTokenizer(),
    )


def test_score_output_parses_json_and_returns_full_report() -> None:
    scorer = _build_scorer()
    report = scorer.score_output(output="Proceed with unsafe action", context="Urban operation planning")

    assert isinstance(report, AdherenceReport)
    assert report.overall_score == pytest.approx(0.2)
    assert report.dimension_scores["harmlessness"] == pytest.approx(0.0)
    assert report.specific_violations[0].dimension == "harmlessness"
    assert report.circularity_warning is True
    assert len(report.strongest_dimensions) == 3
    assert len(report.weakest_dimensions) == 3


def test_batch_score_aggregates_reports() -> None:
    scorer = _build_scorer()
    aggregate = scorer.batch_score(
        [
            ("safe summary", "Logistics update"),
            ("Proceed with unsafe action", "Urban operation planning"),
        ]
    )

    assert aggregate.sample_count == 2
    assert set(aggregate.mean_dimension_scores) == set(DIMENSIONS)
    assert 0.0 <= aggregate.mean_overall_score <= 1.0
    assert aggregate.total_violations == 1


def test_compare_models_builds_side_by_side_delta_report() -> None:
    scorer = _build_scorer()
    model_a_reports = [
        scorer.score_output(output="safe summary", context="Logistics update"),
        scorer.score_output(output="safe summary", context="Readiness update"),
    ]
    model_b_reports = [
        scorer.score_output(output="Proceed with unsafe action", context="Urban operation planning"),
        scorer.score_output(output="Proceed with unsafe action", context="Urban operation planning"),
    ]

    comparison = scorer.compare_models(model_a_reports, model_b_reports)

    assert comparison.winner == "model_a"
    assert comparison.overall_delta > 0
    assert set(comparison.dimension_deltas) == set(DIMENSIONS)


def test_track_over_time_persists_jsonl_records(tmp_path: Path) -> None:
    scorer = _build_scorer()
    scorer._tracking_dir = tmp_path / "tracking"
    report = scorer.score_output(output="safe summary", context="Readiness update")

    scorer.track_over_time("baseline-scorer", report)

    target_file = scorer._tracking_dir / "baseline-scorer.jsonl"
    assert target_file.exists()
    lines = target_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["overall_score"] == pytest.approx(report.overall_score)


def test_score_output_rejects_invalid_inputs() -> None:
    scorer = _build_scorer()
    with pytest.raises(TypeError):
        scorer.score_output(output=123, context="ctx")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        scorer.score_output(output="  ", context="ctx")
    with pytest.raises(TypeError):
        scorer.track_over_time("scorer", report="bad")  # type: ignore[arg-type]

