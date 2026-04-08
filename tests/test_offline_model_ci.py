"""Unit tests for offline model CI pipeline behavior."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load_module():
    module_path = Path("scripts/model_pipeline/offline_model_ci.py").resolve()
    spec = importlib.util.spec_from_file_location("offline_model_ci", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_model_entry_hash_and_from_file(tmp_path: Path) -> None:
    mod = _load_module()
    model_file = tmp_path / "test.gguf"
    model_file.write_bytes(b"abc123")

    entry = mod.ModelEntry.from_file("mixtral", "v1", model_file, "Q4_K_M")

    assert entry.engine_id == "mixtral"
    assert entry.version == "v1"
    assert entry.filename == "test.gguf"
    assert entry.size_bytes == 6
    assert len(entry.sha256) == 64


def test_manifest_register_save_load_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()

    cache_dir = tmp_path / "cache"
    manifest_path = tmp_path / "model_manifest.json"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mod, "CACHE", cache_dir)
    monkeypatch.setattr(mod, "MANIFEST", manifest_path)

    model_file = cache_dir / "phi.gguf"
    model_file.write_bytes(b"phi-model")
    entry = mod.ModelEntry.from_file("phi3_medium", "v1", model_file, "Q4_K_M")

    manifest = mod.ModelManifest()
    manifest.register(entry)
    manifest.save()
    assert manifest_path.exists()

    reloaded = mod.ModelManifest()
    assert reloaded.get("phi3_medium") is not None
    assert reloaded.verify("phi3_medium") is True

    model_file.write_bytes(b"tampered")
    assert reloaded.verify("phi3_medium") is False


def test_package_model_unknown_and_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()
    monkeypatch.setattr(mod, "CACHE", tmp_path / "cache")

    assert mod.package_model("unknown_engine", "v1") is None
    assert mod.package_model("mixtral", "v1", dry_run=True) is None


def test_package_model_returns_cached_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load_module()
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mod, "CACHE", cache_dir)

    cached_file = cache_dir / mod.ENGINE_CONFIGS["mixtral"]["gguf_out"]
    cached_file.write_bytes(b"cached")

    path = mod.package_model("mixtral", "v1", dry_run=False)
    assert path == cached_file


def test_register_and_track_writes_manifest_without_mlflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load_module()

    cache_dir = tmp_path / "cache"
    manifest_path = tmp_path / "model_manifest.json"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mod, "CACHE", cache_dir)
    monkeypatch.setattr(mod, "MANIFEST", manifest_path)

    model_file = cache_dir / "mixtral.gguf"
    model_file.write_bytes(b"mixtral-model")

    # Tactical resilience: simulate air-gapped runtime without MLflow package.
    monkeypatch.delitem(sys.modules, "mlflow", raising=False)

    mod.register_and_track("mixtral", "v5", model_file)

    data = json.loads(manifest_path.read_text())
    assert "mixtral" in data
    assert data["mixtral"]["version"] == "v5"
    assert data["mixtral"]["filename"] == "mixtral.gguf"
