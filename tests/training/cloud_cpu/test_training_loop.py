"""Unit tests for cloud CPU TrainingLoop."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.storage.object_storage import ObjectStorageConnector
from src.training.cloud_cpu.paths import StatePaths, TrainingTrack
from src.training.cloud_cpu.promotion_gate import PromotionGate
from src.training.cloud_cpu.training_loop import PacketTrainingBackend
from src.training.cloud_cpu.training_loop import StubTrainingBackend, TrainingLoop
from src.training.validation.grok_oracle import Verdict


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


class _StubOracle:
    def __init__(self, passed: bool, score: float, reason: str) -> None:
        self._verdict = Verdict(
            artifact_id="unused",
            passed=passed,
            score=score,
            reason=reason,
            criteria_scores={"overall": score},
            evaluated_at="2026-04-24T00:00:00+00:00",
            oracle_mode="offline",
        )

    def evaluate_artifact(self, request, validation_stage: str = "") -> Verdict:
        _ = request
        _ = validation_stage
        return self._verdict


class _GPUQueueProbe:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def queue_cpu_cleared_adapter(self, **kwargs):
        self.calls.append(dict(kwargs))
        return "job-probe"


def _write_min_gate(path: Path) -> None:
    path.write_text("promotion:\n  min_steps: 0\n", encoding="utf-8")


def test_training_loop_uses_packet_backend_when_jsonl_present(tmp_path: Path) -> None:
    state_paths = StatePaths(tmp_path / "state")
    track = TrainingTrack.SAUDI_MOD
    _write_track_scenario(state_paths, track, "scenario-00001", n_rows=4)
    config_path = tmp_path / "track.yaml"
    config_path.write_text("training:\n  micro_batch_size: 2\n", encoding="utf-8")

    loop = TrainingLoop(track=track, config_path=config_path, state_paths=state_paths)
    assert isinstance(loop.backend, PacketTrainingBackend)


def test_training_loop_stage1_passes_to_cpu_cleared_and_gpu_queue(tmp_path: Path) -> None:
    state_paths = StatePaths(tmp_path / "state")
    track = TrainingTrack.NATO
    _write_track_scenario(state_paths, track, "scenario-00001", n_rows=6)
    config_path = tmp_path / "track.yaml"
    config_path.write_text("training:\n  micro_batch_size: 2\n", encoding="utf-8")

    gate_cfg = tmp_path / "promotion_gate.yaml"
    _write_min_gate(gate_cfg)
    promotion_gate = PromotionGate(config_path=gate_cfg, track_config_path=config_path)
    gpu_probe = _GPUQueueProbe()
    connector = ObjectStorageConnector(emulation_root=tmp_path / "object-storage")

    loop = TrainingLoop(
        track=track,
        config_path=config_path,
        state_paths=state_paths,
        oracle=_StubOracle(passed=True, score=0.91, reason="stage1-pass"),
        gpu_orchestrator=gpu_probe,
        promotion_gate=promotion_gate,
        object_storage_connector=connector,
        engine_id="phi3",
        session_id="session-stage1-pass",
        validation_log_path=tmp_path / "state/training/validation_log.jsonl",
    )
    metrics = loop.run_cycle()
    assert metrics.samples_processed == 2
    assert gpu_probe.calls
    assert gpu_probe.calls[0]["track"] == track.value

    adapter_id = f"{track.value}-phi3-{metrics.step:09d}"
    cleared_key = f"training/stage1/cpu_cleared/{track.value}/phi3/{adapter_id}.adapter.json"
    assert connector.exists(cleared_key)


def test_training_loop_stage1_failures_are_logged(tmp_path: Path) -> None:
    state_paths = StatePaths(tmp_path / "state")
    track = TrainingTrack.INDOPAC_MOD
    _write_track_scenario(state_paths, track, "scenario-00001", n_rows=4)
    config_path = tmp_path / "track.yaml"
    config_path.write_text("training:\n  micro_batch_size: 2\n", encoding="utf-8")

    gate_cfg = tmp_path / "promotion_gate.yaml"
    _write_min_gate(gate_cfg)
    promotion_gate = PromotionGate(config_path=gate_cfg, track_config_path=config_path)
    validation_log_path = tmp_path / "state/training/validation_log.jsonl"

    loop = TrainingLoop(
        track=track,
        config_path=config_path,
        state_paths=state_paths,
        oracle=_StubOracle(passed=False, score=0.22, reason="insufficient quality"),
        promotion_gate=promotion_gate,
        object_storage_connector=ObjectStorageConnector(emulation_root=tmp_path / "object-storage"),
        engine_id="phi3",
        session_id="session-stage1-fail",
        validation_log_path=validation_log_path,
    )
    loop.run_cycle()

    lines = [line for line in validation_log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines
    payload = json.loads(lines[-1])
    assert payload["stage"] == "stage_1_cpu"
    assert payload["passed"] is False
    assert "insufficient quality" in payload["reason"]

