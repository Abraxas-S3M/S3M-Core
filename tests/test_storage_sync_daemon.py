"""Unit tests for object storage sync daemon orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts.infra.storage_sync_daemon import StorageSyncDaemon


class _FakeConnector:
    _instance: "_FakeConnector | None" = None

    def __init__(self) -> None:
        self.pull_calls: list[tuple[str, str]] = []
        self.push_calls: list[tuple[str, str]] = []
        self.list_calls: list[str] = []

    @classmethod
    def from_config(cls, _config: dict[str, Any]) -> "_FakeConnector":
        instance = cls()
        _FakeConnector._instance = instance
        return instance

    def list_objects(self, prefix: str) -> list[dict[str, str]]:
        self.list_calls.append(prefix)
        return [{"Key": f"{prefix}file-001.bin"}]

    def sync_prefix_to_local(
        self,
        prefix: str,
        local_dir: str | Path,
        blocked_tokens: list[str] | None = None,
    ) -> dict[str, int]:
        _ = blocked_tokens
        self.pull_calls.append((prefix, str(local_dir)))
        return {"downloaded": 1, "uploaded": 0, "skipped": 0, "bytes_transferred": 100}

    def sync_local_to_prefix(self, local_dir: str | Path, prefix: str) -> dict[str, int]:
        self.push_calls.append((str(local_dir), prefix))
        return {"downloaded": 0, "uploaded": 1, "skipped": 0, "bytes_transferred": 100}


def _write_config(tmp_path: Path, **sync_overrides: Any) -> Path:
    sync = {
        "node_id": "hetzner",
        "tracks": ["saudi_mod", "nato"],
        "quantized_pull_engines": ["phi3-medium", "mistral-7b"],
        "adapters_engine_ids": ["phi3-medium"],
        "engines_blocked_from_pull": ["grok", "grok-300b"],
        "local": {
            "training_root": str(tmp_path / "state" / "training" / "cloud_cpu"),
            "models_root": str(tmp_path / "models"),
            "adapters_root": str(tmp_path / "adapters"),
            "metrics_root": str(tmp_path / "state" / "training" / "cloud_cpu" / "metrics"),
            "gui_snapshots_root": str(tmp_path / "gui-snapshots"),
        },
    }
    sync.update(sync_overrides)
    payload = {
        "object_storage": {
            "endpoint": "https://example.invalid",
            "bucket_name": "s3m-vault",
            "access_key": "key-id",
            "secret_key": "app-key",
        },
        "sync": sync,
    }
    config_path = tmp_path / "object_storage.yaml"
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return config_path


def test_sync_cycle_executes_expected_pull_and_push_operations(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr("scripts.infra.storage_sync_daemon.ObjectStorageConnector", _FakeConnector)

    daemon = StorageSyncDaemon(config_path=str(config_path))
    totals = daemon.sync_cycle()
    connector = _FakeConnector._instance

    pulled_prefixes = [prefix for prefix, _ in connector.pull_calls]
    assert "datasets/saudi_mod/scenarios/" in pulled_prefixes
    assert "datasets/nato/scenarios/" in pulled_prefixes
    assert "models/q4-gguf/phi3-medium/" in pulled_prefixes
    assert "models/q4-gguf/mistral-7b/" in pulled_prefixes
    assert "models/fp16-adapters/phi3-medium/saudi_mod/" in pulled_prefixes
    assert "models/fp16-adapters/phi3-medium/nato/" in pulled_prefixes
    assert all("grok" not in prefix.lower() for prefix in pulled_prefixes)

    pushed_prefixes = [prefix for _, prefix in connector.push_calls]
    assert "checkpoints/hetzner/saudi_mod/" in pushed_prefixes
    assert "checkpoints/hetzner/nato/" in pushed_prefixes
    assert "eval-results/hetzner/global/" in pushed_prefixes
    assert "gui-snapshots/" in pushed_prefixes

    assert totals["downloaded"] >= 1
    assert totals["uploaded"] >= 1
    assert totals["bytes_transferred"] > 0


def test_sync_cycle_blocks_grok_pull_paths_and_logs_warning(tmp_path: Path, monkeypatch, caplog) -> None:
    config_path = _write_config(
        tmp_path,
        quantized_pull_engines=["phi3-medium", "grok-300b"],
        adapters_engine_ids=["grok-300b"],
    )
    monkeypatch.setattr("scripts.infra.storage_sync_daemon.ObjectStorageConnector", _FakeConnector)

    daemon = StorageSyncDaemon(config_path=str(config_path))
    with caplog.at_level("WARNING", logger="s3m.infra.storage_sync"):
        daemon.sync_cycle()
    connector = _FakeConnector._instance

    pulled_prefixes = [prefix for prefix, _ in connector.pull_calls]
    assert "quantized/grok-300b/" not in pulled_prefixes
    assert all("adapters/grok-300b/" not in prefix for prefix in pulled_prefixes)
    assert any("Blocked pull prefix encountered" in record.message for record in caplog.records)


def test_sync_cycle_blocks_when_listed_key_contains_grok(tmp_path: Path, monkeypatch, caplog) -> None:
    class _KeyBlockingConnector(_FakeConnector):
        def list_objects(self, prefix: str) -> list[dict[str, str]]:
            self.list_calls.append(prefix)
            if prefix == "models/q4-gguf/phi3-medium/":
                return [{"Key": "models/q4-gguf/phi3-medium/grok-shadow.bin"}]
            return [{"Key": f"{prefix}file-001.bin"}]

    config_path = _write_config(tmp_path, quantized_pull_engines=["phi3-medium"])
    monkeypatch.setattr("scripts.infra.storage_sync_daemon.ObjectStorageConnector", _KeyBlockingConnector)

    daemon = StorageSyncDaemon(config_path=str(config_path))
    with caplog.at_level("WARNING", logger="s3m.infra.storage_sync"):
        daemon.sync_cycle()
    connector = _KeyBlockingConnector._instance

    pulled_prefixes = [prefix for prefix, _ in connector.pull_calls]
    assert "models/q4-gguf/phi3-medium/" not in pulled_prefixes
    assert any("Blocked pull key encountered" in record.message for record in caplog.records)
