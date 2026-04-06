"""Unit tests for cloud CPU trainer service orchestration."""

from __future__ import annotations

from pathlib import Path
from types import MethodType

from src.training.cloud_cpu.trainer_service import StatePaths, TrainerService, TrainingTrack


def test_run_cycle_updates_state_and_writes_metrics(tmp_path: Path) -> None:
    paths = StatePaths(root=tmp_path / "trainer_state")
    paths.ensure_dirs()
    service = TrainerService(track=TrainingTrack.NATO, paths=paths)
    service._loop.config["training"]["checkpoint_every_n_steps"] = 1
    service._loop.config["training"]["eval_every_n_steps"] = 1
    service._loop.config["training"]["cycle_sleep_seconds"] = 0

    service.run_cycle_once()

    status = service.get_status()
    assert status["track"] == TrainingTrack.NATO.value
    assert status["state"]["current_step"] >= 1
    assert (paths.metrics / "cycles.jsonl").exists()
    runs_dir = paths.for_track(TrainingTrack.NATO).runs
    checkpoints = sorted(runs_dir.glob("checkpoint-*"))
    assert checkpoints


def test_pause_resume_stop_flags(tmp_path: Path) -> None:
    paths = StatePaths(root=tmp_path / "trainer_state")
    paths.ensure_dirs()
    service = TrainerService(track=TrainingTrack.SAUDI_MOD, paths=paths)

    service.pause()
    assert service.get_status()["paused"] is True
    service.resume()
    assert service.get_status()["paused"] is False
    service.stop()
    assert service.get_status()["running"] is False


def test_start_acquires_and_releases_lock(tmp_path: Path) -> None:
    paths = StatePaths(root=tmp_path / "trainer_state")
    paths.ensure_dirs()
    service = TrainerService(track=TrainingTrack.UKRAINE_MOD, paths=paths)

    def _single_cycle_then_stop(self: TrainerService) -> None:
        self._running = False

    service.run_cycle_once = MethodType(_single_cycle_then_stop, service)
    service.start()

    lock_path = paths.locks / f"{TrainingTrack.UKRAINE_MOD.value}.lock"
    assert not lock_path.exists()
