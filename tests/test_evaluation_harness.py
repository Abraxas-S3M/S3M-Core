"""Unit tests for S3M evaluation harness and benchmark gates."""

from __future__ import annotations

import json
from pathlib import Path

from src.evaluation.accuracy_bench import AccuracyBenchmark
from src.evaluation.harness import EvaluationHarness
from src.evaluation.latency_bench import LatencyBenchmark
from src.evaluation.memory_bench import MemoryBenchmark
from src.evaluation.quantization_quality import QuantizationQualityBenchmark


class MockBackend:
    def __init__(self, outputs: dict[str, str] | None = None, log_probs: dict[str, list[float]] | None = None):
        self.outputs = outputs or {}
        self.log_probs = log_probs or {}
        self.loaded = False

    def load_model(self, model_id: str | None = None) -> None:
        self.loaded = True

    def unload_model(self, model_id: str | None = None) -> None:
        self.loaded = False

    def generate(self, prompt: str, model_id: str | None = None) -> str:
        return self.outputs.get(prompt, prompt)

    def get_logprobs(
        self, prompt: str, output: str, model_id: str | None = None
    ) -> list[float]:
        return self.log_probs.get(prompt, [-1.0, -1.1, -1.2])


class CompositeBackend(MockBackend):
    def __init__(self, quant_backend: MockBackend, fp16_backend: MockBackend):
        super().__init__()
        self.quant_backend = quant_backend
        self.fp16_backend = fp16_backend

    def generate(self, prompt: str, model_id: str | None = None) -> str:
        return self.quant_backend.generate(prompt, model_id=model_id)


def _write_test_config(path: Path, max_rss_mb: int = 999999) -> None:
    config_text = f"""
global:
  fail_on_any_violation: true
  report_format: "json"
models:
  phi3-mini:
    latency:
      p50_ms: 10000
      p95_ms: 10000
      p99_ms: 10000
    memory:
      max_rss_mb: {max_rss_mb}
      max_vram_mb: 0
    accuracy:
      min_exact_match_pct: 50.0
      min_f1_pct: 50.0
      regression_tolerance_pct: 5.0
    quantization_quality:
      max_perplexity_increase_pct: 25.0
      min_rouge_l_vs_fp16: 0.5
      min_cosine_sim_vs_fp16: 0.5
"""
    path.write_text(config_text.strip() + "\n", encoding="utf-8")


def test_latency_benchmark_passes_with_relaxed_thresholds() -> None:
    backend = MockBackend()
    result = LatencyBenchmark().run(
        model_id="phi3-mini",
        backend=backend,
        prompts=["one", "two", "three", "four"],
        thresholds={"p50_ms": 10_000, "p95_ms": 10_000, "p99_ms": 10_000},
    )
    assert result.passed is True
    assert len(result.samples) == 4


def test_latency_benchmark_fails_when_thresholds_are_too_low() -> None:
    backend = MockBackend()
    result = LatencyBenchmark().run(
        model_id="phi3-mini",
        backend=backend,
        prompts=["one", "two", "three"],
        thresholds={"p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0},
    )
    assert result.passed is False
    assert any("p50_ms" in violation for violation in result.violations)


def test_memory_benchmark_fails_when_rss_threshold_is_zero() -> None:
    backend = MockBackend()
    result = MemoryBenchmark().run(
        model_id="phi3-mini",
        backend=backend,
        prompts=["status"],
        thresholds={"max_rss_mb": 0.0, "max_vram_mb": 0.0},
    )
    assert result.passed is False
    assert any("rss_peak_mb" in violation for violation in result.violations)


def test_accuracy_benchmark_passes_for_exact_and_f1() -> None:
    backend = MockBackend(outputs={"p1": "alpha bravo", "p2": "charlie delta"})
    test_set = [
        {"prompt": "p1", "expected_output": "alpha bravo"},
        {"prompt": "p2", "expected_output": "charlie delta"},
    ]
    result = AccuracyBenchmark().run(
        model_id="phi3-mini",
        backend=backend,
        test_set=test_set,
        thresholds={"min_exact_match_pct": 100.0, "min_f1_pct": 100.0, "regression_tolerance_pct": 0.0},
    )
    assert result.passed is True
    assert result.exact_match_pct == 100.0
    assert result.f1_pct == 100.0


def test_accuracy_benchmark_handles_arabic_text() -> None:
    backend = MockBackend(outputs={"p": "مرحبا بكم في س٣م"})
    test_set = [{"prompt": "p", "expected_output": "مرحبا بكم في س٣م"}]
    result = AccuracyBenchmark().run(
        model_id="phi3-mini",
        backend=backend,
        test_set=test_set,
        thresholds={"min_exact_match_pct": 100.0, "min_f1_pct": 100.0, "regression_tolerance_pct": 0.0},
    )
    assert result.passed is True
    assert result.exact_match_pct == 100.0
    assert result.f1_pct == 100.0


def test_accuracy_benchmark_detects_regression_from_baseline(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baselines"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    (baseline_dir / "phi3-mini.json").write_text(
        json.dumps({"exact_match_pct": 95.0, "f1_pct": 96.0}),
        encoding="utf-8",
    )
    backend = MockBackend(outputs={"p": "wrong answer"})
    result = AccuracyBenchmark(baseline_dir=str(baseline_dir)).run(
        model_id="phi3-mini",
        backend=backend,
        test_set=[{"prompt": "p", "expected_output": "right answer"}],
        thresholds={"min_exact_match_pct": 0.0, "min_f1_pct": 0.0, "regression_tolerance_pct": 5.0},
    )
    assert result.regression_detected is True
    assert result.passed is False
    assert any("regression" in violation.lower() for violation in result.violations)


def test_quantization_quality_passes_for_similar_outputs() -> None:
    quant = MockBackend(outputs={"p": "mission ready alpha"}, log_probs={"p": [-1.05, -1.00]})
    fp16 = MockBackend(outputs={"p": "mission ready alpha"}, log_probs={"p": [-1.00, -0.95]})
    result = QuantizationQualityBenchmark().run(
        model_id="phi3-mini",
        quant_backend=quant,
        fp16_backend=fp16,
        prompts=["p"],
        thresholds={
            "max_perplexity_increase_pct": 25.0,
            "min_rouge_l_vs_fp16": 0.95,
            "min_cosine_sim_vs_fp16": 0.95,
        },
    )
    assert result.passed is True
    assert result.rouge_l_vs_fp16 >= 0.95
    assert result.cosine_sim_vs_fp16 >= 0.95


def test_quantization_quality_fails_for_divergent_outputs() -> None:
    quant = MockBackend(outputs={"p": "x y z"}, log_probs={"p": [-2.5, -2.7]})
    fp16 = MockBackend(outputs={"p": "mission ready alpha"}, log_probs={"p": [-1.0, -1.0]})
    result = QuantizationQualityBenchmark().run(
        model_id="phi3-mini",
        quant_backend=quant,
        fp16_backend=fp16,
        prompts=["p"],
        thresholds={
            "max_perplexity_increase_pct": 10.0,
            "min_rouge_l_vs_fp16": 0.80,
            "min_cosine_sim_vs_fp16": 0.80,
        },
    )
    assert result.passed is False
    assert len(result.violations) >= 1


def test_evaluation_harness_run_all_and_report_serialization(tmp_path: Path) -> None:
    config_path = tmp_path / "evaluation_thresholds.yaml"
    _write_test_config(config_path, max_rss_mb=999999)

    quant_backend = MockBackend(outputs={"alpha": "alpha", "bravo": "bravo"})
    fp16_backend = MockBackend(outputs={"alpha": "alpha", "bravo": "bravo"})
    backend = CompositeBackend(quant_backend=quant_backend, fp16_backend=fp16_backend)

    harness = EvaluationHarness(config_path=str(config_path))
    report = harness.run_all(
        model_id="phi3-mini",
        backend=backend,
        test_prompts=["alpha", "bravo", "charlie"],
    )

    assert report.passed is True
    json_report = report.to_json()
    markdown_report = report.to_markdown()
    assert '"model_id": "phi3-mini"' in json_report
    assert "# S3M Evaluation Report - phi3-mini" in markdown_report
