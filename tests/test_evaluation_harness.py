"""Unit tests for the S3M evaluation harness."""

from __future__ import annotations

import json
from pathlib import Path
import time

import yaml

from src.evaluation.accuracy_bench import AccuracyBenchmark
from src.evaluation.harness import EvaluationHarness
from src.evaluation.latency_bench import LatencyBenchmark
from src.evaluation.memory_bench import MemoryBenchmark
from src.evaluation.quantization_quality import QuantizationQualityBenchmark


class MockBackend:
    """Deterministic backend for tactical CI benchmark tests."""

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        delay_sec: float = 0.0,
        log_probs: dict[str, list[float]] | None = None,
    ):
        self.responses = responses or {}
        self.delay_sec = delay_sec
        self.log_probs = log_probs or {}
        self.loaded = False
        self.fp16_backend = None

    def load_model(self, model_id: str) -> None:  # noqa: ARG002 - parity with runtime API
        self.loaded = True

    def unload_model(self, model_id: str) -> None:  # noqa: ARG002 - parity with runtime API
        self.loaded = False

    def infer(self, prompt: str) -> dict[str, str]:
        if self.delay_sec > 0:
            time.sleep(self.delay_sec)
        return {"response": self.responses.get(prompt, f"echo:{prompt}")}

    def score_log_probs(self, prompt: str, output: str) -> dict[str, list[float]]:  # noqa: ARG002
        return {"log_probs": self.log_probs.get(prompt, [-1.0, -1.1, -1.2])}


def _write_config(path: Path, config: dict) -> Path:
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_latency_benchmark_passes_with_relaxed_thresholds() -> None:
    benchmark = LatencyBenchmark(thresholds={"p50_ms": 1000, "p95_ms": 1000, "p99_ms": 1000})
    backend = MockBackend(responses={"a": "ok", "b": "ok"}, delay_sec=0.001)
    result = benchmark.run("phi3-mini", backend, ["a", "b", "a", "b"])

    assert result.passed is True
    assert len(result.samples) == 4
    assert result.violations == []


def test_latency_benchmark_detects_percentile_violation() -> None:
    benchmark = LatencyBenchmark(thresholds={"p50_ms": 0.01, "p95_ms": 0.01, "p99_ms": 0.01})
    backend = MockBackend(responses={"a": "ok"}, delay_sec=0.002)
    result = benchmark.run("phi3-mini", backend, ["a", "a", "a", "a"])

    assert result.passed is False
    assert any("p50_ms exceeded" in violation for violation in result.violations)


def test_memory_benchmark_reports_rss_and_passes() -> None:
    benchmark = MemoryBenchmark(thresholds={"max_rss_mb": 999999, "max_vram_mb": 0})
    backend = MockBackend(responses={"a": "ok"})
    result = benchmark.run("phi3-mini", backend, ["a", "a"])

    assert result.passed is True
    assert result.rss_peak_mb >= result.rss_before_mb


def test_memory_benchmark_fails_when_rss_threshold_is_too_low() -> None:
    benchmark = MemoryBenchmark(thresholds={"max_rss_mb": 1, "max_vram_mb": 0})
    backend = MockBackend(responses={"a": "ok"})
    result = benchmark.run("phi3-mini", backend, ["a", "a"])

    assert result.passed is False
    assert any("max_rss_mb exceeded" in violation for violation in result.violations)


def test_accuracy_benchmark_handles_arabic_and_english_token_f1() -> None:
    backend = MockBackend(
        responses={
            "status": "all clear",
            "الحالة": "كل شيء آمن",
        }
    )
    test_set = [
        {"prompt": "status", "expected_output": "all clear"},
        {"prompt": "الحالة", "expected_output": "كل شيء آمن"},
    ]
    benchmark = AccuracyBenchmark(
        thresholds={"min_exact_match_pct": 90.0, "min_f1_pct": 90.0, "regression_tolerance_pct": 5.0}
    )
    result = benchmark.run("phi3-mini", backend, test_set)

    assert result.passed is True
    assert result.exact_match_pct == 100.0
    assert result.f1_pct == 100.0


def test_accuracy_benchmark_detects_regression_from_baseline(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline_payload = {"exact_match_pct": 100.0, "f1_pct": 100.0}
    (baseline_dir / "phi3-mini.json").write_text(json.dumps(baseline_payload), encoding="utf-8")

    backend = MockBackend(responses={"prompt": "wrong answer"})
    test_set = [{"prompt": "prompt", "expected_output": "correct answer"}]
    benchmark = AccuracyBenchmark(
        thresholds={"min_exact_match_pct": 0.0, "min_f1_pct": 0.0, "regression_tolerance_pct": 5.0},
        baseline_dir=baseline_dir,
    )
    result = benchmark.run("phi3-mini", backend, test_set)

    assert result.regression_detected is True
    assert result.passed is False
    assert any("regression exceeded tolerance" in violation for violation in result.violations)


def test_quantization_quality_benchmark_passes_with_similar_outputs() -> None:
    quant_backend = MockBackend(
        responses={"p1": "tactical response ready", "p2": "unit status green"},
        log_probs={"p1": [-1.0, -1.1], "p2": [-1.0, -1.1]},
    )
    fp16_backend = MockBackend(
        responses={"p1": "tactical response ready", "p2": "unit status green"},
        log_probs={"p1": [-1.0, -1.1], "p2": [-1.0, -1.1]},
    )
    benchmark = QuantizationQualityBenchmark(
        thresholds={
            "max_perplexity_increase_pct": 15.0,
            "min_rouge_l_vs_fp16": 0.8,
            "min_cosine_sim_vs_fp16": 0.8,
        }
    )
    result = benchmark.run("phi3-mini", quant_backend, fp16_backend, ["p1", "p2"])

    assert result.passed is True
    assert result.rouge_l_vs_fp16 == 1.0
    assert result.cosine_sim_vs_fp16 == 1.0


def test_quantization_quality_benchmark_fails_on_quality_drop() -> None:
    quant_backend = MockBackend(
        responses={"p1": "bad output", "p2": "noise"},
        log_probs={"p1": [-3.0, -3.0], "p2": [-3.0, -3.0]},
    )
    fp16_backend = MockBackend(
        responses={"p1": "tactical response ready", "p2": "unit status green"},
        log_probs={"p1": [-1.0, -1.0], "p2": [-1.0, -1.0]},
    )
    benchmark = QuantizationQualityBenchmark(
        thresholds={
            "max_perplexity_increase_pct": 10.0,
            "min_rouge_l_vs_fp16": 0.95,
            "min_cosine_sim_vs_fp16": 0.95,
        }
    )
    result = benchmark.run("phi3-mini", quant_backend, fp16_backend, ["p1", "p2"])

    assert result.passed is False
    assert len(result.violations) >= 1


def test_evaluation_harness_run_all_passes_and_serializes() -> None:
    quant_backend = MockBackend(
        responses={"p1": "alpha", "p2": "bravo"},
        log_probs={"p1": [-1.0, -1.0], "p2": [-1.0, -1.0]},
    )
    fp16_backend = MockBackend(
        responses={"p1": "alpha", "p2": "bravo"},
        log_probs={"p1": [-1.0, -1.0], "p2": [-1.0, -1.0]},
    )
    quant_backend.fp16_backend = fp16_backend

    harness = EvaluationHarness()
    report = harness.run_all("phi3-mini", quant_backend, ["p1", "p2"])

    assert report.passed is True
    assert report.violations == []
    assert '"model_id": "phi3-mini"' in report.to_json()
    assert "S3M Evaluation Report" in report.to_markdown()


def test_evaluation_harness_run_all_fails_with_strict_quant_thresholds(tmp_path: Path) -> None:
    config = {
        "global": {"fail_on_any_violation": True, "report_format": "json"},
        "models": {
            "phi3-mini": {
                "latency": {"p50_ms": 1000, "p95_ms": 1000, "p99_ms": 1000},
                "memory": {"max_rss_mb": 999999, "max_vram_mb": 0},
                "accuracy": {
                    "min_exact_match_pct": 0.0,
                    "min_f1_pct": 0.0,
                    "regression_tolerance_pct": 5.0,
                },
                "quantization_quality": {
                    "max_perplexity_increase_pct": 1.0,
                    "min_rouge_l_vs_fp16": 0.99,
                    "min_cosine_sim_vs_fp16": 0.99,
                },
            }
        },
    }
    config_path = _write_config(tmp_path / "eval.yaml", config)

    quant_backend = MockBackend(
        responses={"p1": "noise", "p2": "noise"},
        log_probs={"p1": [-3.0, -3.0], "p2": [-3.0, -3.0]},
    )
    fp16_backend = MockBackend(
        responses={"p1": "alpha bravo", "p2": "charlie delta"},
        log_probs={"p1": [-1.0, -1.0], "p2": [-1.0, -1.0]},
    )
    quant_backend.fp16_backend = fp16_backend

    harness = EvaluationHarness(config_path=str(config_path))
    report = harness.run_all("phi3-mini", quant_backend, ["p1", "p2"])

    assert report.passed is False
    assert any(violation.startswith("quant_quality:") for violation in report.violations)
