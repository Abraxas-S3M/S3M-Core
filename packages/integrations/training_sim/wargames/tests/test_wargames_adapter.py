from __future__ import annotations

from packages.integrations.training_sim.wargames.adapter import WargamesAdapter


def test_manifest_metadata_is_loaded():
    manifest = WargamesAdapter(mode="airgapped").get_manifest()
    assert manifest.slug == "wargames"
    assert manifest.domain == "training_sim"
    assert manifest.license == "Unknown"


def test_validate_availability_true_in_airgapped_mode():
    assert WargamesAdapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    response = WargamesAdapter(mode="airgapped").execute({"operation": "simulate_battle"})
    assert response["source"] == "fixture"
    assert response["result"]["scenario_id"] == "wargames-northern-ridge-2026-04-10"
