"""Unit tests for cloud CPU ResumeManager."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.training.cloud_cpu.paths import StatePaths, TrainingTrack
from src.training.cloud_cpu.resume_manager import ResumeManager


def _write_checkpoint(root: Path, step: int, *, state_blob: bytes, complete: bool = True, valid_sha: bool = True) -> Path:
    checkpoint_dir = root / f"checkpoint-{step:09d}"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    (checkpoint_dir / "state.pt").write_bytes(state_blob)

    digest = hashlib.sha256(state_blob).hexdigest()
    if not valid_sha:
        digest = "0" * 64

    manifest = {
        "checkpoint_id": f"ckpt-{step}",
        "step": step,
        "epoch": max(0, step // 2),
        "loss": 1.0 / max(1, step),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": 1,
        "path": str(checkpoint_dir),
        "sha256": digest,
        "model_id": "model-x",
        "adapter_config_hash": "abcd1234",
        "precision_used": "fp32",
        "peak_memory_mb": 128.0,
        "is_complete": complete,
    }
    (checkpoint_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return checkpoint_dir


def test_resume_ladder_prefers_promoted_then_runs_then_shared(tmp_path: Path) -> None:
    state_paths = StatePaths(tmp_path / "state")
    track = TrainingTrack.SAUDI_MOD
    _write_checkpoint(state_paths.for_track(track).promoted, 3, state_blob=b"promoted")
    _write_checkpoint(state_paths.for_track(track).runs, 9, state_blob=b"runs")
    _write_checkpoint(state_paths.for_track(TrainingTrack.SHARED).promoted, 12, state_blob=b"shared")

    manager = ResumeManager(state_paths)
    chosen = manager.scan_for_resume(track)
    assert chosen is not None
    assert chosen.source == "promoted"
    assert chosen.step == 3


def test_resume_ladder_falls_back_to_runs_then_shared(tmp_path: Path) -> None:
    state_paths = StatePaths(tmp_path / "state")
    track = TrainingTrack.UKRAINE_MOD
    _write_checkpoint(state_paths.for_track(track).runs, 7, state_blob=b"runs")
    _write_checkpoint(state_paths.for_track(TrainingTrack.SHARED).promoted, 5, state_blob=b"shared")

    manager = ResumeManager(state_paths)
    chosen = manager.scan_for_resume(track)
    assert chosen is not None
    assert chosen.source == "latest"
    assert chosen.step == 7

    for path in state_paths.for_track(track).runs.iterdir():
        if path.is_dir():
            for child in path.iterdir():
                child.unlink()
            path.rmdir()

    manager = ResumeManager(state_paths)
    chosen_shared = manager.scan_for_resume(track)
    assert chosen_shared is not None
    assert chosen_shared.source == "shared"
    assert chosen_shared.step == 5


def test_scan_skips_corrupt_latest_checkpoint(tmp_path: Path) -> None:
    state_paths = StatePaths(tmp_path / "state")
    promoted = state_paths.for_track(TrainingTrack.NATO).promoted
    _write_checkpoint(promoted, 4, state_blob=b"valid", valid_sha=True)
    _write_checkpoint(promoted, 8, state_blob=b"corrupt", valid_sha=False)

    manager = ResumeManager(state_paths)
    chosen = manager.scan_for_resume(TrainingTrack.NATO)
    assert chosen is not None
    assert chosen.step == 4


def test_restore_state_increments_resume_count_and_reads_trainer_state(tmp_path: Path) -> None:
    state_paths = StatePaths(tmp_path / "state")
    promoted = state_paths.for_track(TrainingTrack.SHARED).promoted
    checkpoint_dir = _write_checkpoint(promoted, 11, state_blob=b"payload", valid_sha=True)
    trainer_state = {
        "step": 10,
        "epoch": 2,
        "last_loss": 0.77,
        "resume_count": 4,
        "dataset_cursor": {"scenario_idx": 1, "line_idx": 2},
    }
    (checkpoint_dir / "trainer_state.json").write_text(json.dumps(trainer_state), encoding="utf-8")

    manager = ResumeManager(state_paths)
    meta = manager.scan_for_resume(TrainingTrack.SHARED)
    assert meta is not None

    restored = manager.restore_state(meta)
    assert restored.resume_count == 5
    assert restored.step == 11
    assert restored.dataset_cursor["line_idx"] == 2


def test_restore_state_raises_on_sha_mismatch(tmp_path: Path) -> None:
    state_paths = StatePaths(tmp_path / "state")
    promoted = state_paths.for_track(TrainingTrack.SHARED).promoted
    _write_checkpoint(promoted, 2, state_blob=b"payload", valid_sha=False)
    manager = ResumeManager(state_paths)
    meta = manager.scan_for_resume(TrainingTrack.SHARED)
    assert meta is None

    # Force explicit restore call with synthetic metadata to validate guardrail.
    broken_dir = promoted / "checkpoint-000000002"
    broken_manifest = json.loads((broken_dir / "manifest.json").read_text(encoding="utf-8"))
    from src.training.cloud_cpu.contracts import CheckpointMeta  # local import for test clarity

    with pytest.raises(ValueError):
        manager.restore_state(
            CheckpointMeta(
                checkpoint_id=broken_manifest["checkpoint_id"],
                step=broken_manifest["step"],
                epoch=broken_manifest["epoch"],
                loss=broken_manifest["loss"],
                timestamp=broken_manifest["timestamp"],
                level=broken_manifest["level"],
                path=broken_manifest["path"],
                sha256=broken_manifest["sha256"],
                model_id=broken_manifest["model_id"],
                adapter_config_hash=broken_manifest["adapter_config_hash"],
                precision_used=broken_manifest["precision_used"],
                peak_memory_mb=broken_manifest["peak_memory_mb"],
                is_complete=broken_manifest["is_complete"],
                source="manual",
            )
        )


def test_init_cleans_orphan_tmp_dirs(tmp_path: Path) -> None:
    state_paths = StatePaths(tmp_path / "state")
    orphan = state_paths.for_track(TrainingTrack.SAUDI_MOD).runs / "checkpoint-000000001.tmp"
    orphan.mkdir(parents=True, exist_ok=True)
    (orphan / "junk").write_text("x", encoding="utf-8")
    assert orphan.exists()

    ResumeManager(state_paths)
    assert not orphan.exists()

