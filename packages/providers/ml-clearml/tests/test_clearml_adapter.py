from __future__ import annotations

import importlib


def _load():
    adapter_mod = importlib.import_module("packages.providers.ml-clearml.adapter")
    config_mod = importlib.import_module("packages.providers.ml-clearml.config")
    return adapter_mod.ClearMLAdapter, config_mod.ClearMLConfig


def test_manifest_correct() -> None:
    Adapter, _ = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.provider_id == "ml-clearml"
    assert m.tier.value == "FREE"
    assert m.auth_type == "api_key"
    assert m.required_env_vars == ["CLEARML_API_ACCESS_KEY", "CLEARML_API_SECRET_KEY"]
    assert m.optional_env_vars == ["CLEARML_API_HOST"]


def test_s3m_pipelines_defined() -> None:
    _, Config = _load()
    cfg = Config()
    assert len(cfg.s3m_pipelines) == 4
    assert {"sar_retrain", "rul_retrain", "arabic_finetune", "yolo_finetune"}.issubset(cfg.s3m_pipelines.keys())


def test_training_overview_structure() -> None:
    Adapter, _ = _load()
    out = Adapter(mode="airgapped").get_training_overview()
    assert {"experiments", "models", "datasets", "pipelines", "latest_experiment", "active_pipelines"}.issubset(out.keys())


def test_offline_mode_supported(monkeypatch) -> None:
    Adapter, Config = _load()
    monkeypatch.setenv("CLEARML_OFFLINE_MODE", "true")
    cfg = Config()
    health = Adapter(config=cfg, mode="airgapped").health_check()
    assert health["detail"]["offline_mode"] is True


def test_fetch_airgapped() -> None:
    Adapter, _ = _load()
    out = Adapter(mode="airgapped").fetch({"action": "experiments"})
    assert out["count"] > 0

