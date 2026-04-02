"""Tests for sandbox controller container and hot-config logic."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.edge_compute.sandbox_controller import SandboxController


def test_deploy_update_and_stop_without_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.edge_compute.sandbox_controller.shutil.which", lambda _: None)
    controller = SandboxController(runtime="docker", work_dir=str(tmp_path))

    state = controller.deploy(cpu_cores=2, memory_mb=512, params={"temperature": 0.5})
    assert state.running is False
    assert state.parameters["temperature"] == 0.5
    assert Path(state.config_path).exists()

    updated = controller.update_params(state.sandbox_id, {"replication_enabled": True})
    assert updated["replication_enabled"] is True
    assert controller.get_params(state.sandbox_id)["replication_enabled"] is True

    assert controller.stop(state.sandbox_id) is True
    assert controller.list_sandboxes()[0].running is False


def test_deploy_rejects_invalid_parameter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.edge_compute.sandbox_controller.shutil.which", lambda _: None)
    controller = SandboxController(runtime="docker", work_dir=str(tmp_path))
    with pytest.raises(ValueError):
        controller.deploy(params={"max_tokens": 0})


def test_watch_params_polling_triggers_callback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.edge_compute.sandbox_controller.shutil.which", lambda _: None)
    controller = SandboxController(runtime="docker", work_dir=str(tmp_path))
    state = controller.deploy()

    seen: list[dict[str, object]] = []
    started = controller.watch_params(
        state.sandbox_id,
        on_change=lambda params: seen.append(params),
        poll_interval_sec=0.1,
    )
    assert started is True

    params_path = Path(state.config_path)
    with params_path.open("w", encoding="utf-8") as handle:
        payload = dict(state.parameters)
        payload["training_enabled"] = False
        json.dump(payload, handle)

    for _ in range(20):
        if seen:
            break
        time.sleep(0.1)

    assert seen, "watcher should detect config change"
    assert seen[-1]["training_enabled"] is False
    assert controller.stop_watch(state.sandbox_id) is True

