"""Tests for cloud CPU path contracts in tactical training environments."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from src.training.cloud_cpu.paths import StatePaths, TrainingTrack


def test_ensure_dirs_creates_full_state_and_data_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_root = tmp_path / "state"
    data_root = tmp_path / "data"
    monkeypatch.setenv("S3M_STATE_DIR", str(state_root))
    monkeypatch.setenv("S3M_DATA_DIR", str(data_root))

    paths = StatePaths()
    paths.ensure_dirs()

    assert paths.manifests_dir.exists()
    assert paths.metrics_dir.exists()
    assert paths.journal_dir.exists()
    assert paths.locks_dir.exists()
    assert paths.inbox_dir.exists()
    assert paths.processed_dir.exists()
    assert paths.rejected_dir.exists()
    assert paths.evals_dir.exists()

    for track in TrainingTrack:
        checkpoints = paths.for_track(track)
        assert checkpoints.runs.exists()
        assert checkpoints.promoted.exists()
        assert checkpoints.latest.exists()
        assert paths.scenario_dir(track).exists()


def test_for_track_uses_expected_checkpoint_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3M_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("S3M_DATA_DIR", str(tmp_path / "data"))
    paths = StatePaths()

    saudi_paths = paths.for_track(TrainingTrack.SAUDI_MOD)
    expected_base = paths.checkpoints_root / "saudi_mod"
    assert saudi_paths.runs == expected_base / "runs"
    assert saudi_paths.promoted == expected_base / "promoted"
    assert saudi_paths.latest == expected_base / "latest"


def test_state_paths_is_frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3M_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("S3M_DATA_DIR", str(tmp_path / "data"))
    paths = StatePaths()

    with pytest.raises(FrozenInstanceError):
        paths.state_root = Path("/tmp/override")  # type: ignore[misc]
