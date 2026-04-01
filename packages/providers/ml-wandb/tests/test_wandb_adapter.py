from __future__ import annotations

import importlib


def _load():
    adapter_mod = importlib.import_module("packages.providers.ml-wandb.adapter")
    config_mod = importlib.import_module("packages.providers.ml-wandb.config")
    return adapter_mod.WandBAdapter, config_mod.WandBConfig


def test_manifest_correct() -> None:
    Adapter, _ = _load()
    m = Adapter(mode="airgapped").get_manifest()
    assert m.provider_id == "ml-wandb"
    assert m.tier.value == "FREEMIUM"
    assert m.auth_type == "api_key"
    assert m.category.value == "AI_ML_SERVICES"


def test_s3m_projects_defined() -> None:
    _, Config = _load()
    cfg = Config()
    assert len(cfg.s3m_projects) == 6


def test_best_run_selection() -> None:
    Adapter, _ = _load()
    best = Adapter(mode="airgapped").get_best_run("s3m-sar-detection", metric="mAP", direction="max")
    assert abs(float(best["best_run"]["metrics"]["mAP"]) - 0.85) < 1e-9


def test_training_status_all_projects() -> None:
    Adapter, _ = _load()
    status = Adapter(mode="airgapped").get_training_status()
    assert len(status["projects"]) == 6


def test_compare_runs_structure() -> None:
    Adapter, _ = _load()
    out = Adapter(mode="airgapped").compare_runs("s3m-sar-detection", ["sar-run-001", "sar-run-004"])
    assert "runs" in out
    assert "sar-run-001" in out["runs"]
    assert "metrics" in out["runs"]["sar-run-001"]


def test_offline_mode_flag(monkeypatch) -> None:
    Adapter, _ = _load()
    monkeypatch.setenv("WANDB_MODE", "offline")
    health = Adapter(mode="airgapped").health_check()
    assert health["detail"]["offline_mode"] is True


def test_fetch_airgapped() -> None:
    Adapter, _ = _load()
    out = Adapter(mode="airgapped").fetch({"action": "runs", "project": "s3m-sar-detection", "limit": 2})
    assert out["count"] == 2
