"""Latency benchmark primitives for S3M model-gate checks."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np

LOGGER = logging.getLogger("s3m.evaluation.latency_bench")


def _normalize_output(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        for key in ("response", "text", "output", "generated_text"):
            value = raw.get(key)
            if isinstance(value, str):
                return value
    return str(raw)


def _invoke_backend_generate(backend: Any, model_id: str, prompt: str) -> str:
    callables: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    if hasattr(backend, "generate"):
        callables.extend(
            [
                ("generate", (), {"prompt": prompt, "model_id": model_id}),
                ("generate", (prompt,), {"model_id": model_id}),
                ("generate", (), {"prompt": prompt}),
                ("generate", (prompt,), {}),
            ]
        )
    if hasattr(backend, "infer"):
        callables.extend(
            [
                ("infer", (), {"prompt": prompt, "model_id": model_id}),
                ("infer", (prompt,), {"model_id": model_id}),
                ("infer", (), {"prompt": prompt}),
                ("infer", (prompt,), {}),
            ]
        )

    for name, args, kwargs in callables:
        func = getattr(backend, name)
        try:
            return _normalize_output(func(*args, **kwargs))
        except TypeError:
            continue
    raise AttributeError("Backend does not expose a compatible generate/infer signature")


@dataclass(slots=True)
class LatencyResult:
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    samples: list[float] = field(default_factory=list)
    passed: bool = True
    violations: list[str] = field(default_factory=list)


class LatencyBenchmark:
    """Measure mission-response latency percentiles for build-gate enforcement."""

    def __init__(self, warmup_calls: int = 3) -> None:
        self.warmup_calls = max(0, int(warmup_calls))
        np.random.seed(42)

    def run(
        self,
        model_id: str,
        backend: Any,
        prompts: Iterable[str],
        thresholds: dict[str, float],
    ) -> LatencyResult:
        prompt_list = [p for p in prompts if isinstance(p, str)]
        if not prompt_list:
            return LatencyResult(
                p50_ms=0.0,
                p95_ms=0.0,
                p99_ms=0.0,
                mean_ms=0.0,
                passed=False,
                violations=["No prompts provided for latency benchmark"],
            )

        for warmup_index in range(self.warmup_calls):
            prompt = prompt_list[warmup_index % len(prompt_list)]
            try:
                _invoke_backend_generate(backend, model_id, prompt)
            except Exception as exc:  # pragma: no cover - defensive
                LOGGER.warning("Warm-up call failed for %s: %s", model_id, exc)

        samples: list[float] = []
        for prompt in prompt_list:
            start = time.perf_counter()
            _invoke_backend_generate(backend, model_id, prompt)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            samples.append(float(elapsed_ms))

        p50, p95, p99 = np.percentile(np.array(samples), [50, 95, 99]).tolist()
        mean_ms = float(np.mean(samples))

        violations: list[str] = []
        checks = {
            "p50_ms": (float(p50), float(thresholds.get("p50_ms", float("inf")))),
            "p95_ms": (float(p95), float(thresholds.get("p95_ms", float("inf")))),
            "p99_ms": (float(p99), float(thresholds.get("p99_ms", float("inf")))),
        }
        for metric, (value, limit) in checks.items():
            if value > limit:
                violations.append(f"{metric} exceeded threshold ({value:.2f} > {limit:.2f})")

        return LatencyResult(
            p50_ms=float(p50),
            p95_ms=float(p95),
            p99_ms=float(p99),
            mean_ms=mean_ms,
            samples=samples,
            passed=not violations,
            violations=violations,
        )
