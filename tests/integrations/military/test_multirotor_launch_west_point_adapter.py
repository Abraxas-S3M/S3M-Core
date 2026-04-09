from __future__ import annotations

import importlib

import pytest


def _load():
    module = importlib.import_module("packages.integrations.military.multirotor-launch-west-point.adapter")
    return module.MultirotorLaunchwestPointAdapter, module


def test_manifest_is_loaded_from_yaml() -> None:
    adapter_class, _ = _load()
    manifest = adapter_class(mode="airgapped").get_manifest()
    assert manifest.name == "multirotor_launch (West Point)"
    assert manifest.slug == "multirotor-launch-west-point"
    assert manifest.domain == "military"
    assert manifest.source_url == "https://github.com/westpoint-robotics"
    assert manifest.license == "MIT"


def test_logger_name_matches_required_pattern() -> None:
    adapter_class, _ = _load()
    adapter = adapter_class(mode="airgapped")
    assert adapter.logger.name == "s3m.integrations.military.multirotor-launch-west-point"


def test_validate_availability_airgapped_uses_fixture() -> None:
    adapter_class, _ = _load()
    assert adapter_class(mode="airgapped").validate_availability() is True


def test_validate_availability_online_checks_installed_tool(monkeypatch) -> None:
    adapter_class, module = _load()
    monkeypatch.setattr(module.shutil, "which", lambda _cmd: "/usr/bin/mock-tool")
    assert adapter_class(mode="online").validate_availability() is True


def test_execute_airgapped_returns_fixture_payload() -> None:
    adapter_class, _ = _load()
    output = adapter_class(mode="airgapped").execute({"operation": "launch_uav_mission"})
    assert output["status"] == "ok"
    assert output["source"] == "fixture"
    assert output["result"]["mission_id"] == "uav-launch-2026-04-09-wp-014"


def test_execute_rejects_invalid_params() -> None:
    adapter_class, _ = _load()
    adapter = adapter_class(mode="airgapped")
    with pytest.raises(ValueError):
        adapter.execute(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_execute_rejects_path_traversal_launch_file() -> None:
    adapter_class, _ = _load()
    adapter = adapter_class(mode="airgapped")
    with pytest.raises(ValueError):
        adapter.execute({"launch_file": "../secret.launch"})
