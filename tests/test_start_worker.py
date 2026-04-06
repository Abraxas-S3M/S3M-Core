"""Unit tests for the standalone S3M worker process entrypoint."""

from __future__ import annotations

import json
import signal
import sys
import types
from pathlib import Path

from scripts import start_worker


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_scan_replay_data_returns_only_unprocessed(tmp_path) -> None:
    replay_dir = tmp_path / "replays"
    replay_dir.mkdir(parents=True, exist_ok=True)

    pending = replay_dir / "alpha.jsonl"
    processed = replay_dir / "bravo.jsonl"
    pending.write_text('{"features":[1,2,3]}\n', encoding="utf-8")
    processed.write_text('{"features":[4,5,6]}\n', encoding="utf-8")
    processed.with_suffix(".processed").touch()

    start_worker.REPLAY_DIR = replay_dir
    files = start_worker._scan_replay_data()
    assert files == [pending]


def test_run_self_training_cycle_marks_files_processed(tmp_path, monkeypatch) -> None:
    replay_file = tmp_path / "tactical_feed.jsonl"
    _write_jsonl(
        replay_file,
        [
            {"features": [0.1, 0.2, 0.3]},
            {"features": [0.4, 0.5, 0.6]},
            {"features": [0.7, 0.8, 0.9]},
            {"features": "bad-shape"},
        ],
    )

    fake_models = types.ModuleType("src.edge_compute.models")
    fake_models.SelfTrainingStrategy = types.SimpleNamespace(NOISY_STUDENT="noisy_student")

    class _FakeBatch:
        cycle_id = 1
        sample_count = 2
        avg_confidence = 0.8
        noise_applied = True

    class _FakeModel:
        def __init__(self, input_dim: int, hidden_dim: int, output_dim: int) -> None:
            _ = (input_dim, hidden_dim, output_dim)

    class _FakeEngine:
        def __init__(self, strategy) -> None:
            self.strategy = strategy

        def initialize(self, model) -> None:
            _ = model

        def train_cycle(self, labeled_x, labeled_y, unlabeled_x, epochs: int = 1):
            _ = (labeled_x, labeled_y, unlabeled_x, epochs)
            return _FakeBatch()

    fake_self_training = types.ModuleType("src.edge_compute.self_training")
    fake_self_training.NumpyLinearModel = _FakeModel
    fake_self_training.SelfTrainingEngine = _FakeEngine

    monkeypatch.setitem(sys.modules, "src.edge_compute.models", fake_models)
    monkeypatch.setitem(sys.modules, "src.edge_compute.self_training", fake_self_training)

    result = start_worker._run_self_training_cycle([replay_file])
    assert result["status"] == "completed"
    assert result["samples_trained"] == 3
    assert replay_file.with_suffix(".processed").exists()


def test_save_checkpoint_writes_timestamped_payload(tmp_path) -> None:
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    start_worker.CHECKPOINT_DIR = checkpoint_dir

    checkpoint_path = start_worker._save_checkpoint({"status": "completed", "samples_trained": 5})
    assert checkpoint_path is not None
    parsed = json.loads(Path(checkpoint_path).read_text(encoding="utf-8"))

    assert parsed["device"] == start_worker.DEVICE
    assert parsed["deployment_mode"] == start_worker.DEPLOYMENT_MODE
    assert parsed["training_result"]["samples_trained"] == 5


def test_run_evaluation_skips_gpu_probe_in_cpu_mode(tmp_path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text('{"ok": true}', encoding="utf-8")

    start_worker.DEVICE = "cpu"
    result = start_worker._run_evaluation(str(checkpoint))

    assert result["status"] in {"completed", "partial"}
    assert result["metrics"]["gpu_probe_skipped"] is True
    assert result["metrics"]["checkpoint_size_bytes"] > 0


def test_handle_signal_sets_shutdown_flag() -> None:
    start_worker._shutdown_requested = False
    start_worker._handle_signal(signal.SIGTERM, None)
    assert start_worker._shutdown_requested is True
