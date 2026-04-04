"""Unit tests for CPU adaptation evaluation harness gates."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.training.cpu_adaptation.eval_harness import CPUEvaluationHarness


class _Backend:
    def __init__(self, responses: dict[str, str], model: dict[str, list[float]]) -> None:
        self.responses = responses
        self.model = model

    def infer(self, prompt: str) -> dict[str, str]:
        return {"response": self.responses.get(prompt, "")}


def _write_manifest(tmp_path: Path, model_id: str, arabic_support: bool = False) -> None:
    payload = {
        "model_id": model_id,
        "arabic_support": arabic_support,
        "variants": [{"tag": "q4_k_m", "max_ram_mb": 2048}],
        "quality_thresholds": {
            "min_accuracy_pct": 80.0,
            "max_latency_p95_ms": 1000.0,
            "max_memory_mb": 2048.0,
            "accuracy_regression_tolerance_pct": 30.0,
        },
    }
    (tmp_path / f"{model_id}.yaml").write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _q15_model() -> dict[str, list[float]]:
    codebook = [float(i) for i in range(-7, 8)]
    return {
        "layer0.weight": codebook * 3,
        "layer1.weight": codebook * 2,
    }


def test_cpu_eval_harness_run_all_passes(tmp_path: Path) -> None:
    model_id = "tiny-eval"
    prompts = [
        {"prompt": "alpha", "expected_output": "ok:alpha"},
        {"prompt": "bravo", "expected_output": "ok:bravo"},
    ]
    responses = {item["prompt"]: item["expected_output"] for item in prompts}

    _write_manifest(tmp_path, model_id=model_id, arabic_support=False)
    harness = CPUEvaluationHarness(model_id=model_id, manifest_dir=str(tmp_path), sample_size=4, warmup_calls=1)
    report = harness.run_all(backend=_Backend(responses=responses, model=_q15_model()), test_prompts=prompts)
    assert report["passed"] is True
    assert report["violations"] == []


def test_cpu_eval_harness_fails_on_quantization_integrity(tmp_path: Path) -> None:
    model_id = "tiny-eval-quant-fail"
    _write_manifest(tmp_path, model_id=model_id, arabic_support=False)
    harness = CPUEvaluationHarness(model_id=model_id, manifest_dir=str(tmp_path), sample_size=3, warmup_calls=1)
    report = harness.run_all(
        backend=_Backend(responses={"p": "ok:p"}, model={"layer.weight": [0.0, 1.0]}),
        test_prompts=[{"prompt": "p", "expected_output": "ok:p"}],
    )
    assert report["passed"] is False
    assert any("quantization_integrity:" in item for item in report["violations"])


def test_cpu_eval_harness_arabic_gate(tmp_path: Path) -> None:
    model_id = "tiny-arabic"
    _write_manifest(tmp_path, model_id=model_id, arabic_support=True)
    harness = CPUEvaluationHarness(model_id=model_id, manifest_dir=str(tmp_path), sample_size=3, warmup_calls=1)
    report = harness.run_all(
        backend=_Backend(
            responses={
                "prompt": "نجاح",
                "قدّم تحديثًا": "القوة في وضع دفاعي مستقر.",
            },
            model=_q15_model(),
        ),
        test_prompts=[{"prompt": "prompt", "expected_output": "نجاح"}],
        test_prompts_arabic=["قدّم تحديثًا"],
    )
    assert report["checks"]["arabic"]["passed"] is True
