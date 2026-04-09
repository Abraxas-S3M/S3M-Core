from __future__ import annotations

from packages.integrations.navigation.ompl.adapter import OmplAdapter


def test_manifest_metadata_is_loaded() -> None:
    manifest = OmplAdapter(mode="airgapped").get_manifest()
    assert manifest.slug == "ompl"
    assert manifest.domain == "navigation"
    assert manifest.license == "BSD"


def test_validate_availability_true_in_airgapped_mode() -> None:
    assert OmplAdapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    response = OmplAdapter(mode="airgapped").execute({"operation": "plan_path"})
    assert response["source"] == "fixture"
    assert response["result"]["planner"] == "RRTstar"
