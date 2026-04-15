"""Unit tests for Link 22 adapter stub behavior.

Military/tactical context:
These tests lock the Link 22 API contract so coalition tactical workflows can
integrate now and swap in classified parsing later without breaking interfaces.
"""

from __future__ import annotations

import logging

import pytest

from services.interop.link22 import Link22Adapter


def test_connect_forces_stub_mode_and_returns_false(caplog: pytest.LogCaptureFixture) -> None:
    adapter = Link22Adapter({"mode": "integration"})
    with caplog.at_level(logging.WARNING):
        connected = adapter.connect("239.10.22.1:5522")

    assert connected is False
    assert adapter.mode == "stub"
    assert "Link 22 connection requires classified interface — stub mode active" in caplog.text


def test_receive_tracks_returns_empty_list_in_stub_mode() -> None:
    adapter = Link22Adapter({"mode": "stub"})
    assert adapter.receive_tracks() == []


def test_publish_track_logs_and_returns_false_in_stub_mode(caplog: pytest.LogCaptureFixture) -> None:
    adapter = Link22Adapter({"mode": "stub"})
    sample_track = {"id": "track-1", "entity_type": "ENEMY_UAV"}
    with caplog.at_level(logging.INFO):
        published = adapter.publish_track(sample_track)

    assert published is False
    assert "Link 22 stub publish requested for track" in caplog.text
    assert "track-1" in caplog.text


def test_supported_messages_match_stub_contract() -> None:
    adapter = Link22Adapter({"mode": "stub"})
    assert adapter.get_supported_messages() == [
        "F.1 - Unit Position",
        "F.2 - Air Track",
        "F.3 - Surface Track",
        "F.5 - EW Track",
        "F.6 - ACCS Report",
    ]


def test_health_check_reports_classified_stub_status() -> None:
    adapter = Link22Adapter({"mode": "stub"})
    assert adapter.health_check() == {"status": "stub", "reason": "Classified interface not available"}


def test_f_series_to_s3m_entity_mapping_is_documented() -> None:
    adapter = Link22Adapter({"mode": "stub"})
    mapping = adapter.get_message_entity_mapping()

    assert mapping["F.1 - Unit Position"] == ["FRIENDLY_UGV", "ENEMY_UGV"]
    assert mapping["F.2 - Air Track"] == ["FRIENDLY_UAV", "ENEMY_UAV"]
    assert mapping["F.3 - Surface Track"] == ["FRIENDLY_SHIP", "ENEMY_SHIP"]
    assert mapping["F.5 - EW Track"] == ["ENEMY_UAV", "ENEMY_UGV"]
    assert mapping["F.6 - ACCS Report"] == ["CIVILIAN", "UNKNOWN"]


def test_input_validation_rejects_invalid_config_and_track() -> None:
    with pytest.raises(ValueError, match="config must be a dictionary"):
        Link22Adapter(config=None)  # type: ignore[arg-type]

    adapter = Link22Adapter({"mode": "stub"})
    with pytest.raises(ValueError, match="track must be a dictionary"):
        adapter.publish_track(track="invalid")  # type: ignore[arg-type]
