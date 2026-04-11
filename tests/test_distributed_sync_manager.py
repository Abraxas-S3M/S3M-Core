"""Unit tests for distributed weight synchronization manager."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

# Tactical test isolation: provide lightweight boto stubs so sync-manager tests
# can run in offline CI images where cloud SDK packages are intentionally absent.
if "boto3" not in sys.modules:
    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = lambda *args, **kwargs: None
    sys.modules["boto3"] = boto3_stub
if "botocore" not in sys.modules:
    sys.modules["botocore"] = types.ModuleType("botocore")
if "botocore.exceptions" not in sys.modules:
    botocore_exceptions = types.ModuleType("botocore.exceptions")

    class _ClientError(Exception):
        pass

    botocore_exceptions.ClientError = _ClientError
    sys.modules["botocore.exceptions"] = botocore_exceptions

from src.distributed.sync_manager import WeightSyncManager
from src.storage.vault_paths import VaultPaths


class _FakeConnector:
    def __init__(self) -> None:
        self.sync_down_result: list[Path] | dict[str, int] = []
        self.sync_up_result: list[str] | dict[str, int] = []
        self.list_keys_map: dict[str, list[str]] = {}
        self.sync_down_calls: list[tuple[str, Path]] = []
        self.sync_up_calls: list[tuple[Path, str]] = []
        self.upload_calls: list[tuple[Path, str]] = []

    def sync_down(self, remote_prefix: str, local_dir: Path) -> list[Path] | dict[str, int]:
        self.sync_down_calls.append((remote_prefix, local_dir))
        return self.sync_down_result

    def sync_up(self, source_dir: Path, remote_prefix: str) -> list[str] | dict[str, int]:
        self.sync_up_calls.append((source_dir, remote_prefix))
        return self.sync_up_result

    def upload_file(self, local_path: Path, remote_key: str) -> None:
        self.upload_calls.append((local_path, remote_key))

    def list_keys(self, prefix: str) -> list[str]:
        return self.list_keys_map.get(prefix, [])


@pytest.fixture
def distributed_config(tmp_path: Path) -> Path:
    """Write a minimal distributed training config used by sync tests."""
    config_path = tmp_path / "distributed_training.yaml"
    config_path.write_text(
        "\n".join(
            [
                "distributed_training:",
                "  tracks: [saudi_mod, nato]",
                "  training_profiles:",
                "    phi3_medium: {}",
                "    mixtral: {}",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


@pytest.fixture
def manager_with_fake_connector(distributed_config: Path, monkeypatch: pytest.MonkeyPatch):
    """Construct manager with deterministic fake connector behavior."""
    fake = _FakeConnector()
    monkeypatch.setattr("src.distributed.sync_manager.B2Connector", lambda: fake)
    manager = WeightSyncManager(str(distributed_config))
    return manager, fake


def test_init_loads_tracks_engines_and_connector(manager_with_fake_connector):
    """Manager derives track/engine sets from config and initializes connector."""
    manager, fake = manager_with_fake_connector
    assert manager.tracks == ["saudi_mod", "nato"]
    assert manager.engine_ids == ["phi3_medium", "mixtral"]
    assert manager.connector is fake


def test_generate_pull_commands_contains_all_engines(manager_with_fake_connector):
    """Pull commands include all four target engines."""
    manager, _ = manager_with_fake_connector
    commands = manager.generate_pull_commands()
    assert commands["phi3_medium"].startswith("huggingface-cli download microsoft/Phi-3-medium-4k-instruct")
    assert "xai-org/grok-1" in commands["grok1"]
    assert "mistralai/Mixtral-8x7B-Instruct-v0.1" in commands["mixtral"]
    assert "humain-ai/ALLaM-7B-Instruct-preview" in commands["allam"]


def test_estimate_download_time_returns_per_engine_and_totals(manager_with_fake_connector):
    """Download estimate includes each engine and aggregate totals."""
    manager, _ = manager_with_fake_connector
    estimates = manager.estimate_download_time(bandwidth_mbps=200.0)
    assert set(estimates) == {"phi3_medium", "grok1", "mixtral", "allam", "totals"}
    assert estimates["grok1"]["estimated_hours"] > estimates["phi3_medium"]["estimated_hours"]
    assert estimates["totals"]["estimated_minutes"] > 0


def test_pull_from_vault_uses_connector_sync_down(manager_with_fake_connector, tmp_path: Path):
    """Vault pull delegates to connector sync_down with VaultPaths prefix."""
    manager, fake = manager_with_fake_connector
    fake.sync_down_result = [tmp_path / "file1.bin", tmp_path / "file2.bin"]

    target = tmp_path / "target"
    result = manager.pull_from_vault("phi3_medium", str(target), content="base")

    assert result == {"status": "ok", "engine": "phi3_medium", "bytes_transferred": 2}
    assert fake.sync_down_calls == [(VaultPaths.fp16_base("phi3_medium"), target)]


def test_push_to_vault_uses_connector_sync_up(manager_with_fake_connector, tmp_path: Path):
    """Vault push delegates to connector sync_up with adapter prefix."""
    manager, fake = manager_with_fake_connector
    fake.sync_up_result = ["models/fp16-adapters/phi3_medium/x.bin"]
    source = tmp_path / "adapters"
    source.mkdir(parents=True, exist_ok=True)
    (source / "adapter.safetensors").write_text("payload", encoding="utf-8")

    result = manager.push_to_vault("phi3_medium", str(source), content="adapters")

    assert result == {"status": "ok", "engine": "phi3_medium", "bytes_transferred": 1}
    assert fake.sync_up_calls == [(source, VaultPaths.adapters("phi3_medium"))]


def test_check_vault_status_uses_precision_manager(manager_with_fake_connector, monkeypatch: pytest.MonkeyPatch):
    """Status check routes through PrecisionManager inventory API."""
    manager, fake = manager_with_fake_connector
    inventory = {"phi3-medium": {"has_fp16": True, "has_q4": True}}

    class _FakePrecisionManager:
        def __init__(self, connector):
            assert connector is fake

        def get_model_inventory(self):
            return inventory

    monkeypatch.setattr("src.distributed.sync_manager.PrecisionManager", _FakePrecisionManager)
    result = manager.check_vault_status()
    assert result == inventory


def test_engine_weight_status_uses_connector_list_keys(manager_with_fake_connector):
    """Per-engine status is computed from Object Storage key listings."""
    manager, fake = manager_with_fake_connector
    fake.list_keys_map[VaultPaths.fp16_base("phi3_medium")] = ["models/fp16/phi3_medium/config.json"]
    fake.list_keys_map[VaultPaths.q4_serving("mixtral")] = ["models/q4-gguf/mixtral/model.gguf"]

    status = manager.get_engine_weight_status()
    assert status["phi3_medium"]["base"] is True
    assert status["mixtral"]["quantized"] is True
    assert status["allam"]["adapters"] is False


def test_invalid_content_raises_validation_error(manager_with_fake_connector):
    """Invalid content bucket names are rejected for security posture."""
    manager, _ = manager_with_fake_connector
    with pytest.raises(ValueError):
        manager.pull_from_vault("phi3_medium", "models/phi3-medium", content="weights")
