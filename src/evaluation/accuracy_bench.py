"""Accuracy benchmark for bilingual tactical prompt evaluation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("s3m.evaluation.accuracy_bench")


@dataclass(slots=True)
class AccuracyResult:
    """Accuracy and regression outcome for build-gate checks."""

    exact_match_pct: float
    f1_pct: float
    baseline_em: float | None
    baseline_f1: float | None
    regression_detected: bool
    passed: bool
    violations: list[str] = field(default_factory=list)


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def _tokenize(text: str) -> list[str]:
    return _normalize_text(text).split()


def _token_f1(prediction: str, reference: str) -> float:
    pred_tokens = _tokenize(prediction)
    ref_tokens = _tokenize(reference)
    if not pred_tokens and not ref_tokens:
        return 1.0
    if not pred_tokens or not ref_tokens:
        return 0.0

    overlap = Counter(pred_tokens) & Counter(ref_tokens)
    common = float(sum(overlap.values()))
    if common == 0.0:
        return 0.0
    precision = common / float(len(pred_tokens))
    recall = common / float(len(ref_tokens))
    return (2.0 * precision * recall) / (precision + recall)


def _extract_output_text(output: Any) -> str:
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        for key in ("response", "text", "output", "final_answer", "generated_text"):
            value = output.get(key)
            if isinstance(value, str):
                return value
        return str(output)
    for attr in ("response", "text", "output", "final_answer", "generated_text"):
        value = getattr(output, attr, None)
        if isinstance(value, str):
            return value
    return str(output)


def _invoke_backend(backend: Any, prompt: str) -> str:
    for method_name in ("infer", "generate"):
        method = getattr(backend, method_name, None)
        if callable(method):
            return _extract_output_text(method(prompt))
    if callable(backend):
        return _extract_output_text(backend(prompt))
    raise AttributeError("Backend must implement infer(prompt), generate(prompt), or __call__(prompt)")


class AccuracyBenchmark:
    """Evaluate answer faithfulness to protect mission-critical response quality."""

    def __init__(
        self,
        thresholds: dict[str, float] | None = None,
        baseline_dir: str | Path = "configs/evaluation_baselines",
    ):
        self.thresholds = thresholds or {}
        self.baseline_dir = Path(baseline_dir)

    def _load_baseline(self, model_id: str) -> tuple[float | None, float | None]:
        baseline_path = self.baseline_dir / f"{model_id}.json"
        if not baseline_path.exists():
            return None, None

        payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline_em = payload.get("exact_match_pct", payload.get("baseline_em"))
        baseline_f1 = payload.get("f1_pct", payload.get("baseline_f1"))

        em = float(baseline_em) if baseline_em is not None else None
        f1 = float(baseline_f1) if baseline_f1 is not None else None
        return em, f1

    def run(self, model_id: str, backend: Any, test_set: list[dict[str, str]]) -> AccuracyResult:
        if not test_set:
            raise ValueError("test_set must contain at least one test case")

        for idx, row in enumerate(test_set):
            if "prompt" not in row or "expected_output" not in row:
                raise ValueError(f"test_set[{idx}] must contain 'prompt' and 'expected_output'")

        logger.info("Starting accuracy benchmark for model_id=%s", model_id)

        exact_matches = 0
        f1_scores: list[float] = []

        for row in test_set:
            prompt = row["prompt"]
            expected = row["expected_output"]
            predicted = _invoke_backend(backend, prompt)
            if _normalize_text(predicted) == _normalize_text(expected):
                exact_matches += 1
            f1_scores.append(_token_f1(predicted, expected))

        exact_match_pct = (exact_matches / len(test_set)) * 100.0
        f1_pct = (sum(f1_scores) / len(f1_scores)) * 100.0
        baseline_em, baseline_f1 = self._load_baseline(model_id)

        min_em = float(self.thresholds.get("min_exact_match_pct", 0.0))
        min_f1 = float(self.thresholds.get("min_f1_pct", 0.0))
        regression_tolerance = float(self.thresholds.get("regression_tolerance_pct", 0.0))

        violations: list[str] = []
        if exact_match_pct < min_em:
            violations.append(f"exact_match_pct below minimum: {exact_match_pct:.2f} < {min_em:.2f}")
        if f1_pct < min_f1:
            violations.append(f"f1_pct below minimum: {f1_pct:.2f} < {min_f1:.2f}")

        regression_detected = False
        # Tactical continuity check: avoid silent quality drift against trusted baseline.
        if baseline_em is not None and (baseline_em - exact_match_pct) > regression_tolerance:
            regression_detected = True
            violations.append(
                "exact_match_pct regression exceeded tolerance: "
                f"drop {(baseline_em - exact_match_pct):.2f} > {regression_tolerance:.2f}"
            )
        if baseline_f1 is not None and (baseline_f1 - f1_pct) > regression_tolerance:
            regression_detected = True
            violations.append(
                "f1_pct regression exceeded tolerance: "
                f"drop {(baseline_f1 - f1_pct):.2f} > {regression_tolerance:.2f}"
            )

        passed = not violations
        logger.info(
            "Accuracy benchmark finished model_id=%s passed=%s exact_match=%.2f f1=%.2f",
            model_id,
            passed,
            exact_match_pct,
            f1_pct,
        )
        return AccuracyResult(
            exact_match_pct=exact_match_pct,
            f1_pct=f1_pct,
            baseline_em=baseline_em,
            baseline_f1=baseline_f1,
            regression_detected=regression_detected,
            passed=passed,
            violations=violations,
        )
