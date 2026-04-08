"""Tests for additive Stone Soup multi-hypothesis tracker integration."""

from __future__ import annotations

from src.sensor_fusion.multi_hypothesis_tracker import MultiHypothesisTracker


def test_associate_uses_nearest_neighbor_with_distance_gate() -> None:
    tracker = MultiHypothesisTracker(association_distance=50.0)
    tracks = [
        {"track_id": "T1", "position": [0.0, 0.0, 0.0]},
        {"track_id": "T2", "position": [100.0, 100.0, 0.0]},
    ]
    detections = [
        {"detection_id": "D1", "position": [10.0, 0.0, 0.0]},
        {"detection_id": "D2", "position": [130.0, 130.0, 0.0]},
    ]

    result = tracker.associate(tracks, detections)
    assert len(result) == 2
    assert result[0].track_id == "T1"
    assert result[0].detection_id == "D1"
    assert result[0].score > 0.0
    assert result[1].track_id == "T2"
    assert result[1].detection_id is not None


def test_compute_identity_probabilities_normalizes_scores() -> None:
    tracker = MultiHypothesisTracker()
    probs = tracker.compute_identity_probabilities({"friendly": 1.0, "hostile": 3.0})
    assert probs["hostile"] > probs["friendly"]
    assert abs(sum(probs.values()) - 1.0) < 1e-6
