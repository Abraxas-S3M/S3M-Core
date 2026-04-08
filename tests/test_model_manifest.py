"""Unit tests for strict per-model manifest loader."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.edge_runtime.model_manifest import ModelManifest


def _workspace_manifest_dir() -> str:
    return str(Path(__file__).resolve().parents[1] / "configs" / "model_manifests")


def _write_valid_manifest(path: Path, model_id: str = "test-model") -> None:
    payload = {
        "model_id": model_id,
        "provider": "TestProvider",
        "family": "TestFamily",
        "parameters": "1B",
        "variants": [
            {
                "tag": "q4_k_m",
                "runtime_format": "gguf",
                "file": "models/test-model-q4.gguf",
                "size_mb": 1000,
                "max_ram_mb": 1536,
                "cpu_tokens_per_sec": 12.0,
                "gpu_tokens_per_sec": 20.0,
                "requires_gpu": False,
                "max_context": 2048,
            }
        ],
        "adapter_tuning_allowed": True,
        "qat_supported": True,
        "export_targets": ["gguf", "onnx"],
        "primary_domain": "tactical",
        "arabic_support": False,
        "bilingual_ar_en": False,
        "quality_thresholds": {
            "min_accuracy_pct": 70.0,
            "max_latency_p95_ms": 5000,
            "max_memory_mb": 2048,
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_load_all_includes_default_model_manifests() -> None:
    loader = ModelManifest(manifest_dir=_workspace_manifest_dir())
    manifests = loader.load_all()

    assert {"phi3-medium", "mixtral-8x7b", "grok1-314b", "allam-7b"}.issubset(set(manifests.keys()))
    assert manifests["allam-7b"]["arabic_support"] is True
    assert manifests["allam-7b"]["bilingual_ar_en"] is True
    assert manifests["allam-7b"]["primary_domain"] == "arabic_nlp"


def test_missing_manifest_dir_is_handled_gracefully(tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing-manifests"
    loader = ModelManifest(manifest_dir=str(missing_dir))

    assert loader.load_all() == {}
    assert loader.get_manifest("phi3-medium") == {}


def test_invalid_manifest_file_is_skipped(tmp_path: Path) -> None:
    valid_path = tmp_path / "valid.yaml"
    invalid_path = tmp_path / "invalid.yaml"

    _write_valid_manifest(valid_path, model_id="valid-model")
    invalid_path.write_text("model_id: broken-model\nvariants: []\n", encoding="utf-8")

    loader = ModelManifest(manifest_dir=str(tmp_path))
    manifests = loader.load_all()

    assert set(manifests.keys()) == {"valid-model"}


def test_get_best_cpu_variant_respects_ram_budget() -> None:
    loader = ModelManifest(manifest_dir=_workspace_manifest_dir())

    constrained = loader.get_best_cpu_variant("phi3-medium", available_ram_mb=3200)
    roomy = loader.get_best_cpu_variant("phi3-medium", available_ram_mb=4096)

    assert constrained is not None
    assert constrained["tag"] == "q4_k_m"
    assert roomy is not None
    assert roomy["tag"] == "openvino-int8"


def test_validate_thresholds_returns_pass_fail_breakdown() -> None:
    loader = ModelManifest(manifest_dir=_workspace_manifest_dir())

    pass_result = loader.validate_thresholds(
        "phi3-medium",
        latency_ms=1000.0,
        memory_mb=3000.0,
        accuracy_pct=80.0,
    )
    fail_result = loader.validate_thresholds(
        "phi3-medium",
        latency_ms=9000.0,
        memory_mb=7000.0,
        accuracy_pct=60.0,
    )

    assert pass_result["pass"] is True
    assert pass_result["latency_ok"] is True
    assert pass_result["memory_ok"] is True
    assert pass_result["accuracy_ok"] is True

    assert fail_result["pass"] is False
    assert fail_result["latency_ok"] is False
    assert fail_result["memory_ok"] is False
    assert fail_result["accuracy_ok"] is False
