"""Memory benchmark for S3M edge-safe evaluation harness."""

from __future__ import annotations

import logging
import resource
from dataclasses import dataclass, field
from typing import Any, Iterable

from .latency_bench import _invoke_backend_generate

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - optional dependency path
    psutil = None

LOGGER = logging.getLogger("s3m.evaluation.memory_bench")


def _rss_mb() -> float:
    if psutil is not None:
        process = psutil.Process()
        return float(process.memory_info().rss) / (1024.0 * 1024.0)

    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if usage > 10_000_000:
        return float(usage) / (1024.0 * 1024.0)
    return float(usage) / 1024.0


def _try_backend_call(backend: Any, method_name: str, model_id: str) -> None:
    if not hasattr(backend, method_name):
        return
    method = getattr(backend, method_name)
    for args, kwargs in (
        ((), {"model_id": model_id}),
        ((model_id,), {}),
        ((), {}),
    ):
        try:
            method(*args, **kwargs)
            return
        except TypeError:
            continue
    LOGGER.debug("Skipping backend.%s due to unsupported signature", method_name)


@dataclass(slots=True)
class MemoryResult:
    rss_before_mb: float
    rss_loaded_mb: float
    rss_peak_mb: float
    rss_after_mb: float
    delta_mb: float
    passed: bool = True
    violations: list[str] = field(default_factory=list)


class MemoryBenchmark:
    """Track memory envelope against tactical edge deployment limits."""

    def run(
        self,
        model_id: str,
        backend: Any,
        prompts: Iterable[str],
        thresholds: dict[str, float],
    ) -> MemoryResult:
        prompt_list = [p for p in prompts if isinstance(p, str)]
        if not prompt_list:
            return MemoryResult(
                rss_before_mb=0.0,
                rss_loaded_mb=0.0,
                rss_peak_mb=0.0,
                rss_after_mb=0.0,
                delta_mb=0.0,
                passed=False,
                violations=["No prompts provided for memory benchmark"],
            )

        rss_before = _rss_mb()
        _try_backend_call(backend, "load_model", model_id)
        _try_backend_call(backend, "load", model_id)
        rss_loaded = _rss_mb()

        rss_peak = rss_loaded
        for prompt in prompt_list:
            _invoke_backend_generate(backend, model_id, prompt)
            rss_peak = max(rss_peak, _rss_mb())

        _try_backend_call(backend, "unload_model", model_id)
        _try_backend_call(backend, "unload", model_id)
        rss_after = _rss_mb()
        delta_mb = max(0.0, rss_peak - rss_before)

        max_rss_mb = float(thresholds.get("max_rss_mb", float("inf")))
        max_vram_mb = float(thresholds.get("max_vram_mb", 0.0))
        violations: list[str] = []

        if rss_peak > max_rss_mb:
            violations.append(f"rss_peak_mb exceeded threshold ({rss_peak:.2f} > {max_rss_mb:.2f})")

        if max_vram_mb > 0:
            if hasattr(backend, "get_vram_mb"):
                try:
                    vram_used = float(getattr(backend, "get_vram_mb")())
                    if vram_used > max_vram_mb:
                        violations.append(
                            f"vram_mb exceeded threshold ({vram_used:.2f} > {max_vram_mb:.2f})"
                        )
                except Exception as exc:  # pragma: no cover - defensive
                    LOGGER.warning("Failed to collect VRAM usage: %s", exc)
                    violations.append("VRAM threshold configured but VRAM metric unavailable")
            else:
                violations.append("VRAM threshold configured but VRAM metric unavailable")

        return MemoryResult(
            rss_before_mb=rss_before,
            rss_loaded_mb=rss_loaded,
            rss_peak_mb=rss_peak,
            rss_after_mb=rss_after,
            delta_mb=delta_mb,
            passed=not violations,
            violations=violations,
        )
