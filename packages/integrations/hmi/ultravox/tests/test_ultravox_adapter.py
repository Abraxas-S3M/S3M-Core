from __future__ import annotations

from packages.integrations.hmi.ultravox.adapter import UltravoxAdapter


def test_manifest_metadata_is_loaded():
    manifest = UltravoxAdapter(mode="airgapped").get_manifest()
    assert manifest.slug == "ultravox"
    assert manifest.domain == "hmi"
    assert manifest.license == "(Open weights)"


def test_validate_availability_true_in_airgapped_mode():
    assert UltravoxAdapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    response = UltravoxAdapter(mode="airgapped").execute({"operation": "voice_session"})
    assert response["source"] == "fixture"
    assert response["result"]["session_id"] == "uvx-mission-2026-04-09-001"
