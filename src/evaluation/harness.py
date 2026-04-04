"""Unified evaluation harness for S3M CI gates and edge smoke checks."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .accuracy_bench import AccuracyBenchmark, AccuracyResult
from .latency_bench import LatencyBenchmark, LatencyResult
from .memory_bench import MemoryBenchmark, MemoryResult
from .quantization_quality import QuantQualityResult, QuantizationQualityBenchmark

try:
    import yaml  # type: ignore
except ImportError as exc:  # pragma: no cover - optional dependency path
    yaml = None
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None

LOGGER = logging.getLogger("s3m.evaluation.harness")


@runtime_checkable
class InferenceBackend(Protocol):
    def generate(self, prompt: str, **kwargs: Any) -> Any: ...


@dataclass(slots=True)
class HarnessReport:
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
        payload = {
            "model_id": self.model_id,
            "passed": self.passed,
            "violations": self.violations,
            "latency": asdict(self.latency),
            "memory": asdict(self.memory),
            "accuracy": asdict(self.accuracy),
            "quant_quality": asdict(self.quant_quality),
            "timestamp": self.timestamp,
            "duration_sec": self.duration_sec,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        status_icon = "PASS" if self.passed else "FAIL"
        lines = [
            f"# S3M Evaluation Report - {self.model_id}",
            "",
            f"- Verdict: **{status_icon}**",
            f"- Timestamp (UTC): `{self.timestamp}`",
            f"- Duration: `{self.duration_sec:.3f}s`",
            "",
            "## Benchmarks",
            "",
            "| Check | Passed | Details |",
            "|---|---:|---|",
            (
                f"| Latency | {self.latency.passed} | "
                f"p50={self.latency.p50_ms:.2f}ms, p95={self.latency.p95_ms:.2f}ms, "
                f"p99={self.latency.p99_ms:.2f}ms |"
            ),
            (
                f"| Memory | {self.memory.passed} | "
                f"peak_rss={self.memory.rss_peak_mb:.2f}MB, delta={self.memory.delta_mb:.2f}MB |"
            ),
            (
                f"| Accuracy | {self.accuracy.passed} | "
                f"EM={self.accuracy.exact_match_pct:.2f}%, F1={self.accuracy.f1_pct:.2f}% |"
            ),
            (
                f"| Quantization Quality | {self.quant_quality.passed} | "
                f"ROUGE-L={self.quant_quality.rouge_l_vs_fp16:.4f}, "
                f"Cosine={self.quant_quality.cosine_sim_vs_fp16:.4f}, "
                f"PPL Increase={self.quant_quality.perplexity_increase_pct} |"
            ),
            "",
        ]
        if self.violations:
            lines.append("## Violations")
            lines.append("")
            lines.extend([f"- {violation}" for violation in self.violations])
        else:
            lines.extend(["## Violations", "", "- None"])
        return "\n".join(lines)


class EvaluationHarness:
    """Mission-gate harness for latency, memory, accuracy, and quantization checks."""

    def __init__(self, config_path: str = "configs/evaluation_thresholds.yaml") -> None:
        self.config_path = Path(config_path)
        self.config = self._load_config(self.config_path)
        self.latency_benchmark = LatencyBenchmark()
        self.memory_benchmark = MemoryBenchmark()
        self.accuracy_benchmark = AccuracyBenchmark()
        self.quantization_benchmark = QuantizationQualityBenchmark()

    def _load_config(self, config_path: Path) -> dict[str, Any]:
        if yaml is None:
            raise ImportError(
                "PyYAML is required for EvaluationHarness config loading"
            ) from YAML_IMPORT_ERROR
        if not config_path.exists():
            raise FileNotFoundError(f"Evaluation config not found: {config_path}")
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError("Evaluation config must deserialize to a dictionary")
        return payload

    def _model_thresholds(self, model_id: str) -> dict[str, Any]:
        models_cfg = self.config.get("models", {})
        if model_id not in models_cfg:
            available = ", ".join(sorted(models_cfg.keys()))
            raise KeyError(f"Unknown model_id '{model_id}'. Available: {available}")
        return models_cfg[model_id]

    def _coerce_accuracy_test_set(self, test_prompts: list[str]) -> list[dict[str, str]]:
        test_set: list[dict[str, str]] = []
        for item in test_prompts:
            if isinstance(item, dict) and "prompt" in item and "expected_output" in item:
                test_set.append(
                    {"prompt": str(item["prompt"]), "expected_output": str(item["expected_output"])}
                )
            elif isinstance(item, str):
                test_set.append({"prompt": item, "expected_output": item})
            else:
                LOGGER.warning("Skipping unsupported test prompt entry: %r", item)
        if not test_set:
            return []
        return test_set

    def run_latency(self, model_id: str, backend: InferenceBackend, prompts: list[str]) -> LatencyResult:
        model_cfg = self._model_thresholds(model_id)
        return self.latency_benchmark.run(
            model_id=model_id,
            backend=backend,
            prompts=prompts,
            thresholds=model_cfg.get("latency", {}),
        )

    def run_memory(self, model_id: str, backend: InferenceBackend, prompts: list[str]) -> MemoryResult:
        model_cfg = self._model_thresholds(model_id)
        return self.memory_benchmark.run(
            model_id=model_id,
            backend=backend,
            prompts=prompts,
            thresholds=model_cfg.get("memory", {}),
        )

    def run_accuracy(
        self, model_id: str, backend: InferenceBackend, test_set: list[dict[str, str]]
    ) -> AccuracyResult:
        model_cfg = self._model_thresholds(model_id)
        return self.accuracy_benchmark.run(
            model_id=model_id,
            backend=backend,
            test_set=test_set,
            thresholds=model_cfg.get("accuracy", {}),
        )

    def run_quantization_quality(
        self,
        model_id: str,
        quant_backend: InferenceBackend,
        fp16_backend: InferenceBackend,
        prompts: list[str],
    ) -> QuantQualityResult:
        model_cfg = self._model_thresholds(model_id)
        return self.quantization_benchmark.run(
            model_id=model_id,
            quant_backend=quant_backend,
            fp16_backend=fp16_backend,
            prompts=prompts,
            thresholds=model_cfg.get("quantization_quality", {}),
        )

    def run_all(self, model_id: str, backend: InferenceBackend, test_prompts: list[str]) -> HarnessReport:
        start = time.perf_counter()
        latency_result = self.run_latency(model_id, backend, test_prompts)
        memory_result = self.run_memory(model_id, backend, test_prompts)
        test_set = self._coerce_accuracy_test_set(test_prompts)
        accuracy_result = self.run_accuracy(model_id, backend, test_set)

        fp16_backend = getattr(backend, "fp16_backend", backend)
        quant_backend = getattr(backend, "quant_backend", backend)
        quant_quality_result = self.run_quantization_quality(
            model_id=model_id,
            quant_backend=quant_backend,
            fp16_backend=fp16_backend,
            prompts=test_prompts,
        )

        violations: list[str] = []
        if not latency_result.passed:
            violations.extend([f"latency: {msg}" for msg in latency_result.violations])
        if not memory_result.passed:
            violations.extend([f"memory: {msg}" for msg in memory_result.violations])
        if not accuracy_result.passed:
            violations.extend([f"accuracy: {msg}" for msg in accuracy_result.violations])
        if not quant_quality_result.passed:
            violations.extend([f"quantization_quality: {msg}" for msg in quant_quality_result.violations])

        fail_on_any = bool(self.config.get("global", {}).get("fail_on_any_violation", True))
        passed = not violations if fail_on_any else True
        duration_sec = float(time.perf_counter() - start)
        timestamp = datetime.now(timezone.utc).isoformat()
        return HarnessReport(
            model_id=model_id,
            passed=passed,
            violations=violations,
            latency=latency_result,
            memory=memory_result,
            accuracy=accuracy_result,
            quant_quality=quant_quality_result,
            timestamp=timestamp,
            duration_sec=duration_sec,
        )
