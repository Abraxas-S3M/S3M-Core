from __future__ import annotations

from src.training.cloud_cpu.paths import StatePaths, TrainingTrack


def test_state_paths_create_expected_directories(tmp_path) -> None:
    root = tmp_path / "state-root"
    paths = StatePaths(root=root)

    assert paths.root == root
    assert paths.metrics.exists()
    assert paths.locks.exists()
    assert paths.checkpoints.exists()


def test_state_paths_for_track_creates_checkpoint_layout(tmp_path) -> None:
    paths = StatePaths(root=tmp_path / "state")
    track_paths = paths.for_track(TrainingTrack.SAUDI_MOD)

    assert track_paths.base.name == TrainingTrack.SAUDI_MOD.value
    assert track_paths.runs.exists()
    assert track_paths.promoted.exists()
