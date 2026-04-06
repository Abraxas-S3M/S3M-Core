"""Unit tests for cloud CPU TrainingLoop."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.training.cloud_cpu.paths import StatePaths, TrainingTrack
from src.training.cloud_cpu.training_loop import StubTrainingBackend, TrainingLoop


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_track_scenario(state_paths: StatePaths, track: TrainingTrack, scenario: str, n_rows: int) -> None:
    scenario_dir = state_paths.scenario_dir(track) / scenario
    scenario_dir.mkdir(parents=True, exist_ok=True)

    prompts_blob = "\n".join(
        json.dumps({"prompt": f"{track.value}-prompt-{idx}", "weight": 0.8}) for idx in range(n_rows)
    ) + "\n"
    labels_blob = "\n".join(json.dumps({"completion": f"label-{idx}"}) for idx in range(n_rows)) + "\n"

    (scenario_dir / "prompts.jsonl").write_text(prompts_blob, encoding="utf-8")
    (scenario_dir / "labels.jsonl").write_text(labels_blob, encoding="utf-8")
    manifest = {
        "scenario_id": scenario,
        "track": track.value,
        "data_class": "command",
        "checksums": {
            "prompts.jsonl": _sha256_text(prompts_blob),
            "labels.jsonl": _sha256_text(labels_blob),
        },
    }
    (scenario_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_run_cycle_with_data_and_stub_improves_loss(tmp_path: Path) -> None:
    state_paths = StatePaths(tmp_path / "state")
    track = TrainingTrack.SAUDI_MOD
    _write_track_scenario(state_paths, track, "scenario-00001", n_rows=24)

    config_path = tmp_path / "track.yaml"
    config_path.write_text("training:\n  micro_batch_size: 2\n  steps_per_epoch: 3\n", encoding="utf-8")
    loop = TrainingLoop(track=track, config_path=config_path, state_paths=state_paths, device="cpu")

    losses = []
    for _ in range(6):
        metrics = loop.run_cycle()
        losses.append(metrics.loss)
        assert metrics.samples_processed == 2
        assert metrics.track == track.value
        assert metrics.loss > 0.0

    assert losses[-1] < losses[0]


def test_run_cycle_no_data_returns_empty_metrics(tmp_path: Path) -> None:
    state_paths = StatePaths(tmp_path / "state")
    config_path = tmp_path / "track.yaml"
    config_path.write_text("training:\n  micro_batch_size: 4\n", encoding="utf-8")
    loop = TrainingLoop(track=TrainingTrack.SHARED, config_path=config_path, state_paths=state_paths, device="cpu")

    metrics = loop.run_cycle()
    assert metrics.samples_processed == 0
    assert metrics.loss == 0.0


def test_export_and_restore_state_round_trip(tmp_path: Path) -> None:
    state_paths = StatePaths(tmp_path / "state")
    track = TrainingTrack.NATO
    _write_track_scenario(state_paths, track, "scenario-00001", n_rows=8)

    config_path = tmp_path / "track.yaml"
    config_path.write_text("training:\n  micro_batch_size: 2\n", encoding="utf-8")

    backend_a = StubTrainingBackend(track=track.value)
    loop_a = TrainingLoop(track=track, config_path=config_path, state_paths=state_paths, backend=backend_a)
    metrics_a = loop_a.run_cycle()
    assert metrics_a.samples_processed == 2
    saved_state = loop_a.export_state()

    backend_b = StubTrainingBackend(track=track.value)
    loop_b = TrainingLoop(track=track, config_path=config_path, state_paths=state_paths, backend=backend_b)
    loop_b.restore_state(saved_state)
    metrics_b = loop_b.run_cycle()
    assert metrics_b.step == saved_state.step + 1
    assert metrics_b.samples_processed == 2

