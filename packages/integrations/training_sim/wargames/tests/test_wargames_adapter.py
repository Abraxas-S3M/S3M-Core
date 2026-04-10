from __future__ import annotations

import importlib


def _load_adapter():
    module = importlib.import_module("packages.integrations.training_sim.wargames.adapter")
    return module.WargamesAdapter


def test_manifest_metadata_is_loaded() -> None:
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "wargames"
    assert manifest.domain == "training_sim"
    assert manifest.license == "Unknown"


def test_validate_availability_true_in_airgapped_mode() -> None:
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "terrain_force_simulation"})
    assert response["source"] == "fixture"
    assert response["result"]["exercise_id"] == "wargames-ts-2026-0410-1005"
