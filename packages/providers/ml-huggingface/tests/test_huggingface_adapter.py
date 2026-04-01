from __future__ import annotations

import importlib
from pathlib import Path


def _load():
    adapter_mod = importlib.import_module("packages.providers.ml-huggingface.adapter")
    normalizer_mod = importlib.import_module("packages.providers.ml-huggingface.normalizer")
    config_mod = importlib.import_module("packages.providers.ml-huggingface.config")
    return adapter_mod.HuggingFaceAdapter, normalizer_mod.HuggingFaceNormalizer, config_mod.HuggingFaceConfig


def _touch_model(cache_root: Path, repo: str, quantized: bool = False) -> None:
    model_dir = cache_root / repo.replace("/", "--")
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "weights.bin").write_text("stub-weights", encoding="utf-8")
    if quantized:
        (model_dir / "QUANTIZED.flag").write_text("true\n", encoding="utf-8")


def test_manifest_correct() -> None:
    Adapter, _, _ = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.provider_id == "ml-huggingface"
    assert m.tier.value == "FREEMIUM"
    assert m.auth_type == "api_key"
    assert m.optional_env_vars == ["HUGGINGFACE_TOKEN"]
    assert m.category.value == "AI_ML_SERVICES"


def test_s3m_model_registry_complete() -> None:
    _, _, Config = _load()
    cfg = Config()
    assert len(cfg.s3m_model_registry) == 9
    for _, payload in cfg.s3m_model_registry.items():
        assert {"repo", "pipeline", "layer"}.issubset(payload.keys())


def test_check_model_cached(tmp_path: Path) -> None:
    Adapter, _, Config = _load()
    cfg = Config(local_cache_dir=str(tmp_path))
    adapter = Adapter(config=cfg, mode="airgapped")
    model_id = "microsoft/Phi-3-mini-4k-instruct"
    assert adapter.check_model_cached(model_id) is False
    (tmp_path / model_id.replace("/", "--")).mkdir(parents=True)
    assert adapter.check_model_cached(model_id) is True


def test_model_status_reports_all(tmp_path: Path) -> None:
    Adapter, _, Config = _load()
    cfg = Config(local_cache_dir=str(tmp_path))
    adapter = Adapter(config=cfg, mode="airgapped")
    status = adapter.get_s3m_model_status()
    assert len(status["models"]) == 9
    assert set(status["models"].keys()) == set(cfg.s3m_model_registry.keys())


def test_cache_complete_flag(tmp_path: Path) -> None:
    Adapter, _, Config = _load()
    cfg = Config(local_cache_dir=str(tmp_path))
    adapter = Adapter(config=cfg, mode="airgapped")
    partial = adapter.get_s3m_model_status()
    assert partial["cache_complete"] is False

    for payload in cfg.s3m_model_registry.values():
        _touch_model(tmp_path, str(payload["repo"]), quantized=bool(payload.get("quantized", False)))
    full = adapter.get_s3m_model_status()
    assert full["cache_complete"] is True


def test_normalize_inference_by_task() -> None:
    _, Normalizer, _ = _load()
    n = Normalizer()
    assert "generated_text" in n.normalize_inference_result({"result": [{"generated_text": "ok"}]}, "text-generation")
    assert "summary" in n.normalize_inference_result({"result": [{"summary_text": "sum"}]}, "summarization")
    assert "predictions" in n.normalize_inference_result({"result": [{"token_str": "x"}]}, "fill-mask")
    assert "detections" in n.normalize_inference_result({"result": [{"label": "ship"}]}, "object-detection")
    assert "transcription" in n.normalize_inference_result({"result": {"text": "abc"}}, "automatic-speech-recognition")


def test_generate_manifest(tmp_path: Path) -> None:
    Adapter, _, Config = _load()
    manifest_path = tmp_path / "manifest.yaml"
    cfg = Config(local_cache_dir=str(tmp_path / "models"), offline_model_manifest_path=str(manifest_path))
    adapter = Adapter(config=cfg, mode="airgapped")
    model_dir = tmp_path / "models" / "microsoft--Phi-3-mini-4k-instruct"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "weights.bin").write_text("abc", encoding="utf-8")
    manifest = adapter.generate_offline_manifest()
    assert manifest_path.exists()
    assert "models" in manifest
    assert "microsoft/Phi-3-mini-4k-instruct" in manifest["models"]


def test_fetch_airgapped_reads_manifest(tmp_path: Path) -> None:
    Adapter, _, Config = _load()
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        "generated_at: '2026-01-01T00:00:00Z'\n"
        "models:\n"
        "  microsoft/Phi-3-mini-4k-instruct:\n"
        "    pipeline_tag: text-generation\n"
        "    tags: [language:en]\n"
        "    downloads: 100\n"
        "    size_mb: 123.4\n"
        "    files: [config.json]\n"
        "    card_summary: test\n",
        encoding="utf-8",
    )
    cfg = Config(local_cache_dir=str(tmp_path / "models"), offline_model_manifest_path=str(manifest_path))
    adapter = Adapter(config=cfg, mode="airgapped")
    info = adapter.fetch({"action": "model_info", "model_id": "microsoft/Phi-3-mini-4k-instruct"})
    assert info["model_id"] == "microsoft/Phi-3-mini-4k-instruct"
    assert info["pipeline_tag"] == "text-generation"
