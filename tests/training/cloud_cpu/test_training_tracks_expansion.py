"""Tests for expanded cloud CPU training track definitions.

Military/tactical context:
Expanded regional tracks must remain available to orchestration so doctrine
adaptation can be segmented by theater without manual code edits.
"""

from __future__ import annotations

from src.training.cloud_cpu.paths import TrainingTrack


def test_training_track_enum_includes_new_theater_tracks() -> None:
    values = {track.value for track in TrainingTrack}
    assert "indopac_mod" in values
    assert "southam_mod" in values
    assert "africa_mod" in values

