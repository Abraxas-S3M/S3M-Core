"""Unit tests for distributed weight synchronization manager."""

from dataclasses import dataclass

import pytest

from src.distributed.sync_manager import WeightSyncManager


@dataclass
class _RunResult:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


@pytest.fixture
def distributed_config(tmp_path):
    """Write a minimal distributed training config used by sync tests."""
    config_path = tmp_path / "distributed_training.yaml"
    config_path.write_text(
        "\n".join(
            [
                "distributed_training:",
                "  vault_ip: 10.0.0.8",
                "  hetzner_ip: 10.0.0.9",
                "  vault_base_path: /srv/vault/weights",
                "  vault_user: s3m",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def test_init_loads_primary_vault_settings(distributed_config):
    """Manager loads vault connectivity settings from config."""
    manager = WeightSyncManager(str(distributed_config))
    assert manager.vault_ip == "10.0.0.8"
    assert manager.hetzner_ip == "10.0.0.9"
    assert manager.vault_base_path == "/srv/vault/weights"


def test_generate_pull_commands_contains_all_engines(distributed_config):
    """Pull commands include all four target engines."""
    manager = WeightSyncManager(str(distributed_config))
    commands = manager.generate_pull_commands()
    assert commands["phi3_medium"].startswith("huggingface-cli download microsoft/Phi-3-medium-4k-instruct")
    assert "xai-org/grok-1" in commands["grok1"]
    assert "mistralai/Mixtral-8x7B-Instruct-v0.1" in commands["mixtral"]
    assert "humain-ai/ALLaM-7B-Instruct-preview" in commands["allam"]


def test_estimate_download_time_returns_per_engine_and_totals(distributed_config):
    """Download estimate includes each engine and aggregate totals."""
    manager = WeightSyncManager(str(distributed_config))
    estimates = manager.estimate_download_time(bandwidth_mbps=200.0)
    assert set(estimates) == {"phi3_medium", "grok1", "mixtral", "allam", "totals"}
    assert estimates["grok1"]["estimated_hours"] > estimates["phi3_medium"]["estimated_hours"]
    assert estimates["totals"]["estimated_minutes"] > 0


def test_pull_and_push_parse_rsync_transfer_bytes(distributed_config, monkeypatch, tmp_path):
    """Rsync output is parsed into deterministic byte counters."""
    manager = WeightSyncManager(str(distributed_config))
    source = tmp_path / "adapters"
    source.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "target"

    def _fake_run(cmd, capture_output, text, check):
        if cmd[0] == "rsync":
            return _RunResult(
                returncode=0,
                stdout="Total transferred file size: 12,345 bytes\n",
                stderr="",
            )
        return _RunResult(returncode=1, stdout="", stderr="unexpected command")

    monkeypatch.setattr("src.distributed.sync_manager.subprocess.run", _fake_run)
    pull_result = manager.pull_from_vault("phi3_medium", str(target), content="base")
    push_result = manager.push_to_vault("phi3_medium", str(source), content="adapters")

    assert pull_result == {"status": "ok", "engine": "phi3_medium", "bytes_transferred": 12345}
    assert push_result == {"status": "ok", "engine": "phi3_medium", "bytes_transferred": 12345}


def test_check_vault_status_and_engine_weight_status(distributed_config, monkeypatch):
    """SSH probes map disk and per-engine availability fields."""
    manager = WeightSyncManager(str(distributed_config))

    def _fake_run(cmd, capture_output, text, check):
        remote_cmd = cmd[2]
        if "df -BG" in remote_cmd:
            return _RunResult(returncode=0, stdout="120 880\n", stderr="")
        if "ls -1" in remote_cmd:
            return _RunResult(returncode=0, stdout="phi3_medium\nmixtral\n", stderr="")
        if "test -d" in remote_cmd and "phi3_medium/base" in remote_cmd:
            return _RunResult(returncode=0, stdout="1\n", stderr="")
        if "test -d" in remote_cmd and "mixtral/quantized" in remote_cmd:
            return _RunResult(returncode=0, stdout="1\n", stderr="")
        if "test -d" in remote_cmd:
            return _RunResult(returncode=0, stdout="0\n", stderr="")
        return _RunResult(returncode=1, stdout="", stderr="unsupported")

    monkeypatch.setattr("src.distributed.sync_manager.subprocess.run", _fake_run)

    vault_status = manager.check_vault_status()
    engine_status = manager.get_engine_weight_status()

    assert vault_status["disk_used_gb"] == 120.0
    assert vault_status["disk_free_gb"] == 880.0
    assert vault_status["engines"]["phi3_medium"]["available"] is True
    assert vault_status["engines"]["grok1"]["available"] is False

    assert engine_status["phi3_medium"]["base"] is True
    assert engine_status["mixtral"]["quantized"] is True
    assert engine_status["allam"]["adapters"] is False


def test_invalid_content_raises_validation_error(distributed_config):
    """Invalid content bucket names are rejected for security posture."""
    manager = WeightSyncManager(str(distributed_config))
    with pytest.raises(ValueError):
        manager.pull_from_vault("phi3_medium", "models/phi3-medium", content="weights")
