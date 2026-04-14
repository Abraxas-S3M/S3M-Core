"""Unit tests for track-to-genome/prediction bridge behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.predictive_defense.track_genome_bridge import TrackGenomeBridge
from src.sensor_fusion.models import Track, TrackState


def _make_track(
    *,
    track_id: str = "trk-001",
    velocity: tuple[float, float, float] = (30.0, 40.0, 0.0),
    position: tuple[float, float, float] = (100.0, 200.0, 300.0),
    classification: str | None = "HOSTILE_UAV",
    confidence: float = 0.9,
    seconds_offset: int = 0,
) -> Track:
    now = datetime.now(timezone.utc) + timedelta(seconds=seconds_offset)
    return Track(
        track_id=track_id,
        state=TrackState.CONFIRMED,
        position=position,
        velocity=velocity,
        covariance=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        last_update=now,
        sensor_sources=["radar-1"],
        classification=classification,
        confidence=confidence,
    )


def test_track_to_entity_snapshot_populates_expected_fields() -> None:
    bridge = TrackGenomeBridge()
    snapshot = bridge.track_to_entity_snapshot(_make_track())

    assert snapshot.entity_id == "trk-001"
    assert snapshot.entity_type == "HOSTILE_UAV"
    assert snapshot.position == (100.0, 200.0, 300.0)
    assert snapshot.speed_mps == pytest.approx(50.0, rel=1e-6)
    assert snapshot.heading_deg == pytest.approx(36.8698976, rel=1e-6)
    assert snapshot.threat_level == "high"
    assert snapshot.behavior_tags == ["hostile_uav"]
    assert snapshot.confidence == pytest.approx(0.9, rel=1e-6)
    assert snapshot.volatility == pytest.approx(0.3, rel=1e-6)
    assert snapshot.history == []


def test_track_to_entity_snapshot_uses_recent_history_and_bounds_buffer() -> None:
    bridge = TrackGenomeBridge()

    for i in range(55):
        bridge.track_to_entity_snapshot(
            _make_track(
                track_id="trk-history",
                velocity=(10.0 + i, 5.0 + i, 0.0),
                seconds_offset=i,
            )
        )

    snapshot = bridge.track_to_entity_snapshot(
        _make_track(
            track_id="trk-history",
            velocity=(70.0, 10.0, 0.0),
            seconds_offset=56,
        )
    )

    assert len(snapshot.history) == 10
    assert snapshot.history[-1].speed_mps > snapshot.history[0].speed_mps
    assert len(bridge._track_history["trk-history"]) == 50  # noqa: SLF001


def test_track_to_genome_features_includes_uav_behavior_tags() -> None:
    bridge = TrackGenomeBridge()
    features = bridge.track_to_genome_features(_make_track(classification="enemy_uav"))

    assert features["source_type"] == "sensor_fusion"
    assert features["classification"] == "enemy_uav"
    assert "enemy_uav" in features["behavior_tags"]
    assert "drone" in features["behavior_tags"]
    assert "uav" in features["behavior_tags"]
    assert features["extracted_signature_features"]["speed_range_mps"] == pytest.approx(50.0, rel=1e-6)
    assert features["raw_confidence"] == pytest.approx(0.9, rel=1e-6)


def test_classification_to_threat_level_maps_expected_categories() -> None:
    bridge = TrackGenomeBridge()
    assert bridge._classification_to_threat_level("cruise_missile") == "critical"  # noqa: SLF001
    assert bridge._classification_to_threat_level("uav") == "high"  # noqa: SLF001
    assert bridge._classification_to_threat_level("unknown") == "low"  # noqa: SLF001
    assert bridge._classification_to_threat_level("small_boat") == "medium"  # noqa: SLF001


def test_track_validation_rejects_non_track_input() -> None:
    bridge = TrackGenomeBridge()

    with pytest.raises(ValueError, match="Track instance"):
        bridge.track_to_entity_snapshot(track="not-a-track")  # type: ignore[arg-type]
