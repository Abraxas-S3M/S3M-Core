"""Memory benchmarking for edge deployment safety checks."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import resource
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency
    psutil = None

logger = logging.getLogger("s3m.evaluation.memory_bench")


@dataclass(slots=True)
class MemoryResult:
    """Resident memory profile used for tactical readiness gates."""

    rss_before_mb: float
    rss_loaded_mb: float
    rss_peak_mb: float
    rss_after_mb: float
    delta_mb: float
    passed: bool
    violations: list[str] = field(default_factory=list)


def _memory_mb() -> float:
    if psutil is not None:
        return float(psutil.Process().memory_info().rss) / (1024.0 * 1024.0)

    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KB, while some systems report bytes.
    if usage > 10_000_000:
        return float(usage) / (1024.0 * 1024.0)
    return float(usage) / 1024.0


def _call_backend_load(backend: Any, model_id: str) -> None:
    for method_name in ("load_model", "load", "initialize"):
        method = getattr(backend, method_name, None)
        if callable(method):
            try:
                method(model_id)
            except TypeError:
                method()
            return


def _call_backend_unload(backend: Any, model_id: str) -> None:
    for method_name in ("unload_model", "unload", "teardown"):
        method = getattr(backend, method_name, None)
        if callable(method):
            try:
                method(model_id)
            except TypeError:
                method()
            return


def _invoke_backend(backend: Any, prompt: str) -> None:
    for method_name in ("infer", "generate"):
        method = getattr(backend, method_name, None)
        if callable(method):
            method(prompt)
            return
    if callable(backend):
        backend(prompt)
        return
    raise AttributeError("Backend must implement infer(prompt), generate(prompt), or __call__(prompt)")


class MemoryBenchmark:
    """Monitor RSS headroom so edge nodes avoid mission-time OOM conditions."""

    def __init__(self, thresholds: dict[str, float] | None = None):
        self.thresholds = thresholds or {}

    def run(self, model_id: str, backend: Any, prompts: list[str]) -> MemoryResult:
        if not prompts:
            raise ValueError("prompts must contain at least one prompt")

        logger.info("Starting memory benchmark for model_id=%s", model_id)
        rss_before = _memory_mb()
        rss_loaded = rss_before
        rss_peak = rss_before
        rss_after = rss_before

        try:
            _call_backend_load(backend, model_id)
            rss_loaded = _memory_mb()
            rss_peak = max(rss_peak, rss_loaded)

            for prompt in prompts:
                _invoke_backend(backend, prompt)
                rss_peak = max(rss_peak, _memory_mb())
        finally:
            _call_backend_unload(backend, model_id)
            rss_after = _memory_mb()

        delta_mb = rss_peak - rss_before
        violations: list[str] = []
        max_rss_mb = self.thresholds.get("max_rss_mb")
        max_vram_mb = self.thresholds.get("max_vram_mb", 0)

        if max_rss_mb is not None and rss_peak > float(max_rss_mb):
            violations.append(f"max_rss_mb exceeded: {rss_peak:.2f} > {float(max_rss_mb):.2f}")

        if float(max_vram_mb) > 0:
            current_vram = 0.0
            vram_reader = getattr(backend, "get_vram_mb", None)
            if callable(vram_reader):
                current_vram = float(vram_reader())
            if current_vram > float(max_vram_mb):
                violations.append(f"max_vram_mb exceeded: {current_vram:.2f} > {float(max_vram_mb):.2f}")

        passed = not violations
        logger.info(
            "Memory benchmark finished model_id=%s passed=%s peak=%.2fMB",
            model_id,
            passed,
            rss_peak,
        )
        return MemoryResult(
            rss_before_mb=rss_before,
            rss_loaded_mb=rss_loaded,
            rss_peak_mb=rss_peak,
            rss_after_mb=rss_after,
            delta_mb=delta_mb,
            passed=passed,
            violations=violations,
        )
