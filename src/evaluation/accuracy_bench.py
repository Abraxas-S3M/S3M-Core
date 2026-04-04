"""Accuracy benchmark for model-gate correctness and regression checks."""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .latency_bench import _invoke_backend_generate

LOGGER = logging.getLogger("s3m.evaluation.accuracy_bench")


def _normalize_text(text: str) -> str:
    return " ".join(str(text).strip().split()).casefold()


def _tokenize(text: str) -> list[str]:
    return _normalize_text(text).split()


def _exact_match(predicted: str, expected: str) -> bool:
    return _normalize_text(predicted) == _normalize_text(expected)


def _token_f1(predicted: str, expected: str) -> float:
    pred_tokens = _tokenize(predicted)
    exp_tokens = _tokenize(expected)
    if not pred_tokens and not exp_tokens:
        return 1.0
    if not pred_tokens or not exp_tokens:
        return 0.0

    pred_counts = Counter(pred_tokens)
    exp_counts = Counter(exp_tokens)
    overlap = sum((pred_counts & exp_counts).values())
    if overlap == 0:
        return 0.0

    precision = overlap / len(pred_tokens)
    recall = overlap / len(exp_tokens)
    return (2 * precision * recall) / (precision + recall)


@dataclass(slots=True)
class AccuracyResult:
    exact_match_pct: float
    f1_pct: float
    baseline_em: float | None
    baseline_f1: float | None
    regression_detected: bool
    passed: bool
    violations: list[str] = field(default_factory=list)


class AccuracyBenchmark:
    """Validate mission-task output correctness and detect tactical regressions."""

    def __init__(self, baseline_dir: str = "configs/evaluation_baselines") -> None:
        self.baseline_dir = Path(baseline_dir)
        np.random.seed(42)

    def _load_baseline(self, model_id: str) -> tuple[float | None, float | None]:
        baseline_path = self.baseline_dir / f"{model_id}.json"
        if not baseline_path.exists():
            return None, None
        try:
            payload = json.loads(baseline_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to parse baseline for %s: %s", model_id, exc)
            return None, None

        baseline_em = payload.get("exact_match_pct", payload.get("em_pct", payload.get("exact_match")))
        baseline_f1 = payload.get("f1_pct", payload.get("f1"))
        em_value = float(baseline_em) if baseline_em is not None else None
        f1_value = float(baseline_f1) if baseline_f1 is not None else None
        return em_value, f1_value

    def run(
        self,
        model_id: str,
        backend: Any,
        test_set: list[dict[str, str]],
        thresholds: dict[str, float],
    ) -> AccuracyResult:
        if not test_set:
            return AccuracyResult(
                exact_match_pct=0.0,
                f1_pct=0.0,
                baseline_em=None,
                baseline_f1=None,
                regression_detected=False,
                passed=False,
                violations=["No test samples provided for accuracy benchmark"],
            )

        exact_hits = 0
        f1_scores: list[float] = []
        for row in test_set:
            prompt = str(row.get("prompt", ""))
            expected = str(row.get("expected_output", ""))
            predicted = _invoke_backend_generate(backend, model_id, prompt)
            exact_hits += int(_exact_match(predicted, expected))
            f1_scores.append(_token_f1(predicted, expected))

        exact_match_pct = 100.0 * (exact_hits / len(test_set))
        f1_pct = 100.0 * float(np.mean(f1_scores))

        violations: list[str] = []
        min_exact = float(thresholds.get("min_exact_match_pct", 0.0))
        min_f1 = float(thresholds.get("min_f1_pct", 0.0))
        if exact_match_pct < min_exact:
            violations.append(
                f"exact_match_pct below threshold ({exact_match_pct:.2f} < {min_exact:.2f})"
            )
        if f1_pct < min_f1:
            violations.append(f"f1_pct below threshold ({f1_pct:.2f} < {min_f1:.2f})")

        baseline_em, baseline_f1 = self._load_baseline(model_id)
        tolerance = float(thresholds.get("regression_tolerance_pct", 0.0))
        regression_detected = False
        if baseline_em is not None and (baseline_em - exact_match_pct) > tolerance:
            regression_detected = True
            violations.append(
                f"Exact-match regression exceeded tolerance ({baseline_em - exact_match_pct:.2f} > {tolerance:.2f})"
            )
        if baseline_f1 is not None and (baseline_f1 - f1_pct) > tolerance:
            regression_detected = True
            violations.append(
                f"F1 regression exceeded tolerance ({baseline_f1 - f1_pct:.2f} > {tolerance:.2f})"
            )

        return AccuracyResult(
            exact_match_pct=exact_match_pct,
            f1_pct=f1_pct,
            baseline_em=baseline_em,
            baseline_f1=baseline_f1,
            regression_detected=regression_detected,
            passed=not violations,
            violations=violations,
        )
