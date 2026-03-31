"""Tests for S3M Phase 5 sensor fusion foundation."""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.sensor_fusion.ekf_filter import EKFFilter
from src.sensor_fusion.models import SensorReading, SensorType, Track, TrackState
from src.sensor_fusion.sensor_manager import SensorManager
from src.sensor_fusion.track_fuser import TrackFuser


def _reading(sensor_id: str, x: float, y: float, z: float = 0.0, classification: str | None = None) -> SensorReading:
    data = {"classification": classification} if classification else {}
    return SensorReading(
        sensor_id=sensor_id,
        sensor_type=SensorType.RADAR,
        timestamp=datetime.now(timezone.utc),
        data=data,
        position=(x, y, z),
        confidence=0.9,
    )


def test_ekf_predict_update_cycle():
    ekf = EKFFilter(dt=0.1)
    ekf.reset([0.0, 0.0, 0.0, 1.0, 1.0, 0.0])
    ekf.predict()
    ekf.update([1.0, 1.0, 0.0])
    state = ekf.get_state()
    assert "position" in state and "velocity" in state and "covariance" in state
    assert len(state["position"]) == 3


def test_track_fuser_association_two_near_readings_single_track():
    fuser = TrackFuser(association_threshold=50.0, max_tracks=100)
    tracks = fuser.update([_reading("r1", 10.0, 10.0), _reading("r1", 12.0, 11.0)])
    assert len(tracks) == 1


def test_track_fuser_far_readings_create_two_tracks():
    fuser = TrackFuser(association_threshold=5.0, max_tracks=100)
    tracks = fuser.update([_reading("r1", 0.0, 0.0), _reading("r1", 100.0, 100.0)])
    assert len(tracks) == 2


def test_track_state_transitions_tentative_confirmed_lost_deleted():
    fuser = TrackFuser(association_threshold=50.0, max_tracks=100)
    # Tentative -> confirmed after 3 updates
    for _ in range(3):
        tracks = fuser.update([_reading("r1", 5.0, 5.0)])
    assert len(tracks) == 1
    track_id = tracks[0].track_id
    assert tracks[0].state == TrackState.CONFIRMED

    # Force stale timeout to LOST
    fuser._tracks[track_id].last_update = datetime.now(timezone.utc) - timedelta(seconds=11)
    fuser.update([])
    assert fuser._tracks[track_id].state == TrackState.LOST

    # Force stale timeout to DELETED
    fuser._tracks[track_id].last_update = datetime.now(timezone.utc) - timedelta(seconds=31)
    fuser.update([])
    assert fuser.get_track(track_id) is None


def test_sensor_manager_register_ingest_process():
    manager = SensorManager()
    manager.register_sensor("eo-1", SensorType.EO_CAMERA, {"fov": 90})
    reading = manager.ingest(
        sensor_id="eo-1",
        data={"classification": "tank"},
        position=(100.0, 200.0, 0.0),
        confidence=0.88,
    )
    assert reading.sensor_id == "eo-1"
    tracks = manager.process()
    assert len(tracks) == 1
    assert manager.get_sensors()[0]["sensor_id"] == "eo-1"
