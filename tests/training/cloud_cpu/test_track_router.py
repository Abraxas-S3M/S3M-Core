"""Unit tests for cloud CPU TrackRouter."""

from __future__ import annotations

import json
from pathlib import Path

from src.training.cloud_cpu.paths import StatePaths, TrainingTrack
from src.training.cloud_cpu.track_router import TrackRouter


def _write_pack(inbox: Path, name: str, track: str, with_labels: bool = True) -> Path:
    pack = inbox / name
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "manifest.json").write_text(json.dumps({"track": track}), encoding="utf-8")
    (pack / "prompts.jsonl").write_text('{"prompt":"x"}\n', encoding="utf-8")
    if with_labels:
        (pack / "labels.jsonl").write_text('{"completion":"y"}\n', encoding="utf-8")
    return pack


def test_route_inbox_routes_valid_and_rejects_invalid(tmp_path: Path) -> None:
    state_paths = StatePaths(tmp_path / "state")
    _write_pack(state_paths.inbox, "scenario-00001", TrainingTrack.SAUDI_MOD.value)
    _write_pack(state_paths.inbox, "scenario-00002", "unknown_track")
    _write_pack(state_paths.inbox, "scenario-00003", TrainingTrack.NATO.value, with_labels=False)

    router = TrackRouter(paths=state_paths)
    counts = router.route_inbox()

    assert counts[TrainingTrack.SAUDI_MOD.value] == 1
    assert (state_paths.scenario_dir(TrainingTrack.SAUDI_MOD) / "scenario-00001").exists()

    rejected_root = state_paths.rejected / "inbox"
    assert rejected_root.exists()
    rejected_names = {path.name for path in rejected_root.iterdir()}
    assert "scenario-00002" in rejected_names
    assert "scenario-00003" in rejected_names


def test_route_inbox_rejects_bad_directory_name(tmp_path: Path) -> None:
    state_paths = StatePaths(tmp_path / "state")
    _write_pack(state_paths.inbox, "bad-pack-name", TrainingTrack.SHARED.value)

    counts = TrackRouter(paths=state_paths).route_inbox()
    assert counts[TrainingTrack.SHARED.value] == 0
    assert (state_paths.rejected / "inbox" / "bad-pack-name").exists()

