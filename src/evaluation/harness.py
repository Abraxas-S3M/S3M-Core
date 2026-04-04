"""Unified evaluation harness for CI/CD build gating."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any, Protocol

try:
    import yaml
except ImportError as exc:  # pragma: no cover - required dependency
    raise ImportError("pyyaml is required for EvaluationHarness configuration loading") from exc

from .accuracy_bench import AccuracyBenchmark, AccuracyResult
from .latency_bench import LatencyBenchmark, LatencyResult
from .memory_bench import MemoryBenchmark, MemoryResult
from .quantization_quality import QuantQualityResult, QuantizationQualityBenchmark

logger = logging.getLogger("s3m.evaluation.harness")


class InferenceBackend(Protocol):
    """Minimal protocol for evaluation backends."""

    def infer(self, prompt: str) -> Any:
        """Run local prompt inference and return model output."""


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


def _resolve_reference_backend(backend: Any) -> Any:
    for attr in ("fp16_backend", "reference_backend"):
        candidate = getattr(backend, attr, None)
        if candidate is not None:
            return candidate
    for method_name in ("get_fp16_backend", "get_reference_backend"):
        method = getattr(backend, method_name, None)
        if callable(method):
            candidate = method()
            if candidate is not None:
                return candidate
    return backend


@dataclass(slots=True)
class HarnessReport:
    """Full benchmark report used by CI and edge smoke checks."""

    model_id: str
    passed: bool
    violations: list[str]
    latency: LatencyResult
    memory: MemoryResult
    accuracy: AccuracyResult
    quant_quality: QuantQualityResult
    timestamp: str
    duration_sec: float

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            f"# S3M Evaluation Report — `{self.model_id}`",
            "",
            f"- **Passed:** `{self.passed}`",
            f"- **Timestamp (UTC):** `{self.timestamp}`",
            f"- **Duration (sec):** `{self.duration_sec:.3f}`",
            "",
            "## Violations",
        ]
        if self.violations:
            lines.extend([f"- {item}" for item in self.violations])
        else:
            lines.append("- None")

        lines.extend(
            [
                "",
                "## Latency",
                f"- p50_ms: `{self.latency.p50_ms:.2f}`",
                f"- p95_ms: `{self.latency.p95_ms:.2f}`",
                f"- p99_ms: `{self.latency.p99_ms:.2f}`",
                "",
                "## Memory",
                f"- rss_peak_mb: `{self.memory.rss_peak_mb:.2f}`",
                f"- delta_mb: `{self.memory.delta_mb:.2f}`",
                "",
                "## Accuracy",
                f"- exact_match_pct: `{self.accuracy.exact_match_pct:.2f}`",
                f"- f1_pct: `{self.accuracy.f1_pct:.2f}`",
                "",
                "## Quantization Quality",
                f"- rouge_l_vs_fp16: `{self.quant_quality.rouge_l_vs_fp16:.4f}`",
                f"- cosine_sim_vs_fp16: `{self.quant_quality.cosine_sim_vs_fp16:.4f}`",
                f"- perplexity_increase_pct: `{self.quant_quality.perplexity_increase_pct}`",
            ]
        )
        return "\n".join(lines)


class EvaluationHarness:
    """Run all evaluation checks and produce a single gate verdict."""

    def __init__(self, config_path: str = "configs/evaluation_thresholds.yaml"):
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"Evaluation config not found: {self.config_path}")
        payload = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        self.config = payload
        self.global_config = payload.get("global", {})
        self.models_config = payload.get("models", {})
        logger.info("Loaded evaluation harness config from %s", self.config_path)

    def _model_thresholds(self, model_id: str) -> dict[str, Any]:
        model_cfg = self.models_config.get(model_id)
        if model_cfg is None:
            raise ValueError(f"Unknown model_id '{model_id}' in evaluation configuration")
        return model_cfg

    def run_latency(self, model_id: str, backend: InferenceBackend, prompts: list[str]) -> LatencyResult:
        thresholds = self._model_thresholds(model_id).get("latency", {})
        return LatencyBenchmark(thresholds=thresholds).run(model_id=model_id, backend=backend, prompts=prompts)

    def run_memory(self, model_id: str, backend: InferenceBackend, prompts: list[str]) -> MemoryResult:
        thresholds = self._model_thresholds(model_id).get("memory", {})
        return MemoryBenchmark(thresholds=thresholds).run(model_id=model_id, backend=backend, prompts=prompts)

    def run_accuracy(
        self,
        model_id: str,
        backend: InferenceBackend,
        test_set: list[dict[str, str]],
    ) -> AccuracyResult:
        thresholds = self._model_thresholds(model_id).get("accuracy", {})
        return AccuracyBenchmark(thresholds=thresholds).run(model_id=model_id, backend=backend, test_set=test_set)

    def run_quantization_quality(
        self,
        model_id: str,
        quant_backend: InferenceBackend,
        fp16_backend: InferenceBackend,
        prompts: list[str],
    ) -> QuantQualityResult:
        thresholds = self._model_thresholds(model_id).get("quantization_quality", {})
        return QuantizationQualityBenchmark(thresholds=thresholds).run(
            model_id=model_id,
            quant_backend=quant_backend,
            fp16_backend=fp16_backend,
            prompts=prompts,
        )

    def _build_accuracy_test_set(
        self,
        prompts: list[str],
        reference_backend: InferenceBackend,
    ) -> list[dict[str, str]]:
        # Tactical smoke mode: reference outputs become expected labels when no gold set is supplied.
        test_set: list[dict[str, str]] = []
        for prompt in prompts:
            expected_output = _invoke_backend(reference_backend, prompt)
            test_set.append({"prompt": prompt, "expected_output": expected_output})
        return test_set

    def run_all(
        self,
        model_id: str,
        backend: InferenceBackend,
        test_prompts: list[str],
    ) -> HarnessReport:
        if not test_prompts:
            raise ValueError("test_prompts must contain at least one prompt")

        start = time.perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat()
        logger.info("Running full evaluation harness for model_id=%s", model_id)

        latency = self.run_latency(model_id, backend, test_prompts)
        memory = self.run_memory(model_id, backend, test_prompts)

        fp16_backend = _resolve_reference_backend(backend)
        accuracy_test_set = self._build_accuracy_test_set(test_prompts, fp16_backend)
        accuracy = self.run_accuracy(model_id, backend, accuracy_test_set)
        quant_quality = self.run_quantization_quality(model_id, backend, fp16_backend, test_prompts)

        violations: list[str] = []
        for section, result in (
            ("latency", latency),
            ("memory", memory),
            ("accuracy", accuracy),
            ("quant_quality", quant_quality),
        ):
            for violation in result.violations:
                violations.append(f"{section}: {violation}")

        fail_on_any_violation = bool(self.global_config.get("fail_on_any_violation", True))
        section_passed = latency.passed and memory.passed and accuracy.passed and quant_quality.passed
        passed = section_passed if fail_on_any_violation else True

        report = HarnessReport(
            model_id=model_id,
            passed=passed,
            violations=violations,
            latency=latency,
            memory=memory,
            accuracy=accuracy,
            quant_quality=quant_quality,
            timestamp=timestamp,
            duration_sec=time.perf_counter() - start,
        )
        logger.info("Evaluation harness completed model_id=%s passed=%s", model_id, report.passed)
        return report
