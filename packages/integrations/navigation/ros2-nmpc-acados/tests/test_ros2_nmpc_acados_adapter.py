from __future__ import annotations

import importlib


def _load_adapter():
    module = importlib.import_module("packages.integrations.navigation.ros2-nmpc-acados.adapter")
    return module.Ros2NmpcAcadosAdapter


def test_manifest_metadata_is_loaded() -> None:
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "ros2-nmpc-acados"
    assert manifest.domain == "navigation"
    assert manifest.license == "MIT"


def test_validate_availability_true_in_airgapped_mode() -> None:
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "trajectory_tracking"})
    assert response["source"] == "fixture"
    assert response["result"]["mission_id"] == "s3m-nav-nmpc-dd-041"
