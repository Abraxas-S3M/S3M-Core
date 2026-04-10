from __future__ import annotations

from packages.integrations.core_tooling.mergekit.adapter import MergekitAdapter


def test_manifest_metadata_is_loaded():
    manifest = MergekitAdapter(mode="airgapped").get_manifest()
    assert manifest.slug == "mergekit"
    assert manifest.domain == "core_tooling"
    assert manifest.license == "Unknown"


def test_validate_availability_true_in_airgapped_mode():
    assert MergekitAdapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    response = MergekitAdapter(mode="airgapped").execute({"operation": "ties_merge_probe"})
    assert response["source"] == "fixture"
    assert response["result"]["event_id"] == "mergekit-ct-2026-04-10-001"
