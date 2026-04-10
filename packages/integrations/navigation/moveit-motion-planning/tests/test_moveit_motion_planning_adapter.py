from __future__ import annotations

import importlib


def _load_adapter():
    module = importlib.import_module("packages.integrations.navigation.moveit-motion-planning.adapter")
    return module.MoveitmotionPlanningAdapter


def test_manifest_metadata_is_loaded() -> None:
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "moveit-motion-planning"
    assert manifest.domain == "navigation"
    assert manifest.license == "BSD"


def test_validate_availability_true_in_airgapped_mode() -> None:
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "plan_path"})
    assert response["source"] == "fixture"
    assert response["result"]["event_id"] == "moveit-nav-2026-04-10-001"
