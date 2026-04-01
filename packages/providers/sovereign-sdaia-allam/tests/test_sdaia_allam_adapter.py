from __future__ import annotations

import importlib
from pathlib import Path


def _load():
    adapter_mod = importlib.import_module("packages.providers.sovereign-sdaia-allam.adapter")
    cfg_mod = importlib.import_module("packages.providers.sovereign-sdaia-allam.config")
    test_set_mod = importlib.import_module("packages.providers.sovereign-sdaia-allam.arabic_test_set")
    return adapter_mod.SDAIAAllamAdapter, cfg_mod.SDAIAAllamConfig, cfg_mod, test_set_mod


def test_manifest_correct():
    Adapter, _, _, _ = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.provider_id == "sovereign-sdaia-allam"
    assert m.tier.value == "GOVERNMENT"
    assert m.category.value == "SOVEREIGN_REGIONAL"
    assert "arabic" in m.tags and "saudi" in m.tags


def test_works_without_api_credentials(tmp_path: Path):
    Adapter, Config, _, _ = _load()
    model_dir = tmp_path / "models" / "arabic" / "allam"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "weights-int8.bin").write_bytes(b"0" * 1024)
    adapter = Adapter(config=Config(local_model_dir=str(model_dir)), mode="airgapped")
    assert adapter.validate_credentials() is True


def test_local_model_status():
    Adapter, _, _, _ = _load()
    status = Adapter(mode="airgapped").get_local_model_status()
    assert status["total_cached"] >= 1
    model = status["models"]["allam-7b"]
    assert model["cached"] is True
    assert model["quantization"] in {"int8", "int4", "fp16"}
    assert "vram_gb" in model


def test_allam_health_structure():
    Adapter, _, _, _ = _load()
    out = Adapter(mode="airgapped").get_allam_health()
    for key in ["engine_status", "model_version", "vram_used_gb", "avg_latency_ms", "arabic_quality_score", "last_inference"]:
        assert key in out


def test_benchmark_test_set_present():
    _, _, _, test_set_mod = _load()
    data = test_set_mod.MILITARY_ARABIC_TEST_SET
    assert {"summarization", "entity_extraction", "translation", "command_classification"}.issubset(data.keys())


def test_benchmark_summarization_samples():
    _, _, _, test_set_mod = _load()
    assert len(test_set_mod.MILITARY_ARABIC_TEST_SET["summarization"]) >= 2


def test_benchmark_entity_extraction_samples():
    _, _, _, test_set_mod = _load()
    sample = test_set_mod.MILITARY_ARABIC_TEST_SET["entity_extraction"][0]
    assert len(sample["expected_entities"]) >= 1


def test_benchmark_translation_pairs():
    _, _, _, test_set_mod = _load()
    assert len(test_set_mod.MILITARY_ARABIC_TEST_SET["translation"]) >= 5


def test_benchmark_command_classification():
    _, _, _, test_set_mod = _load()
    assert len(test_set_mod.MILITARY_ARABIC_TEST_SET["command_classification"]) >= 4


def test_usage_report_contexts():
    Adapter, _, cfg_mod, _ = _load()
    report = Adapter(mode="airgapped").get_usage_report()
    assert set(cfg_mod.S3M_ALLAM_USAGE.keys()).issubset(set(report["by_context"].keys()))


def test_model_update_check_airgapped():
    Adapter, _, _, _ = _load()
    update = Adapter(mode="airgapped").check_model_update(current_version="2024.06.01")
    assert update["update_available"] is False
    assert "Air-gapped mode" in update.get("note", "")


def test_allam_models_defined():
    _, _, cfg_mod, _ = _load()
    assert "allam-7b" in cfg_mod.ALLAM_MODELS
    assert "allam-7b-chat" in cfg_mod.ALLAM_MODELS
    assert "vram_int8_gb" in cfg_mod.ALLAM_MODELS["allam-7b"]


def test_recommended_quantization_for_jetson():
    _, _, cfg_mod, _ = _load()
    assert cfg_mod.ALLAM_MODELS["allam-7b"]["recommended_quantization"] == "int8"
