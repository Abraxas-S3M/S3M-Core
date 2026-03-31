"""Unit tests for dead reckoning fallback."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from src.navigation.localization.dead_reckoning import DeadReckoning
from src.navigation.models import Pose


def test_initial_pose_at_origin() -> None:
    dr = DeadReckoning()
    pose = dr.get_pose()
    assert pose.position == (0.0, 0.0, 0.0)


def test_zero_acceleration_maintains_position() -> None:
    dr = DeadReckoning()
    for _ in range(10):
        dr.update((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.1)
    pose = dr.get_pose()
    assert abs(pose.position[0]) < 1e-6
    assert abs(pose.position[1]) < 1e-6


def test_constant_acceleration_increases_velocity_and_position() -> None:
    dr = DeadReckoning()
    for _ in range(10):
        dr.update((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.1)
    pose = dr.get_pose()
    assert pose.velocity[0] > 0.0
    assert pose.position[0] > 0.0


def test_confidence_decays_over_time() -> None:
    dr = DeadReckoning()
    initial = dr.get_pose().confidence
    for _ in range(5):
        dr.update((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.1)
    assert dr.get_pose().confidence < initial


def test_correct_resets_position_from_external_source() -> None:
    dr = DeadReckoning()
    dr.update((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0)
    ext_pose = Pose(
        position=(100.0, 50.0, 5.0),
        orientation=(0.0, 0.0, 0.5),
        velocity=(0.0, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
        timestamp=datetime.now(timezone.utc),
        confidence=0.9,
        source="gps",
    )
    dr.correct(ext_pose)
    pose = dr.get_pose()
    assert pose.position == (100.0, 50.0, 5.0)


def test_get_drift_time_tracks_since_last_correction() -> None:
    dr = DeadReckoning()
    dr.update((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0.5)
    assert dr.get_drift_time() >= 0.5
    ext_pose = Pose(
        position=(0.0, 0.0, 0.0),
        orientation=(0.0, 0.0, 0.0),
        velocity=(0.0, 0.0, 0.0),
        angular_velocity=(0.0, 0.0, 0.0),
        timestamp=datetime.now(timezone.utc),
        confidence=1.0,
        source="gps",
    )
    dr.correct(ext_pose)
    assert dr.get_drift_time() == 0.0
