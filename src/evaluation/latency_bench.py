"""Latency benchmarking for tactical inference readiness gates."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any

import numpy as np

logger = logging.getLogger("s3m.evaluation.latency_bench")


@dataclass(slots=True)
class LatencyResult:
    """Percentile latency summary used by build gates."""

    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    samples: list[float]
    passed: bool
    violations: list[str] = field(default_factory=list)


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


class LatencyBenchmark:
    """Measure inference response envelopes for mission-time constraints."""

    def __init__(self, thresholds: dict[str, float] | None = None, warmup_calls: int = 3):
        self.thresholds = thresholds or {}
        self.warmup_calls = max(0, int(warmup_calls))

    def run(self, model_id: str, backend: Any, prompts: list[str]) -> LatencyResult:
        if not prompts:
            raise ValueError("prompts must contain at least one prompt")

        logger.info("Starting latency benchmark for model_id=%s", model_id)

        for idx in range(self.warmup_calls):
            prompt = prompts[idx % len(prompts)]
            _invoke_backend(backend, prompt)

        samples: list[float] = []
        for prompt in prompts:
            start = time.perf_counter()
            _invoke_backend(backend, prompt)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            samples.append(float(elapsed_ms))

        p50 = float(np.percentile(samples, 50))
        p95 = float(np.percentile(samples, 95))
        p99 = float(np.percentile(samples, 99))
        mean_ms = float(np.mean(samples))

        violations: list[str] = []
        threshold_p50 = self.thresholds.get("p50_ms")
        threshold_p95 = self.thresholds.get("p95_ms")
        threshold_p99 = self.thresholds.get("p99_ms")

        # Tactical gate: percentile breaches imply delayed command-response loops.
        if threshold_p50 is not None and p50 > float(threshold_p50):
            violations.append(f"p50_ms exceeded: {p50:.2f} > {float(threshold_p50):.2f}")
        if threshold_p95 is not None and p95 > float(threshold_p95):
            violations.append(f"p95_ms exceeded: {p95:.2f} > {float(threshold_p95):.2f}")
        if threshold_p99 is not None and p99 > float(threshold_p99):
            violations.append(f"p99_ms exceeded: {p99:.2f} > {float(threshold_p99):.2f}")

        passed = not violations
        logger.info(
            "Latency benchmark finished model_id=%s passed=%s p50=%.2f p95=%.2f p99=%.2f",
            model_id,
            passed,
            p50,
            p95,
            p99,
        )
        return LatencyResult(
            p50_ms=p50,
            p95_ms=p95,
            p99_ms=p99,
            mean_ms=mean_ms,
            samples=samples,
            passed=passed,
            violations=violations,
        )
