"""Unit tests for two-stage hybrid orchestrator pipeline wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.storage.object_storage import ObjectStorageConnector
from src.training.gpu.hybrid_orchestrator import HybridOrchestrator
from src.training.validation.grok_oracle import Verdict


class _TrainerPassStub:
    def __init__(self, engine_id: str) -> None:
        self._engine_id = engine_id

    def train(self, dataset_path: str, resume_from=None):  # noqa: ANN001
        _ = dataset_path
        _ = resume_from
        adapter_dir = Path("tmp-adapters-pass") / self._engine_id
        adapter_dir.mkdir(parents=True, exist_ok=True)
        (adapter_dir / "adapter.bin").write_text("gpu-adapter", encoding="utf-8")
        return {"adapter_path": str(adapter_dir), "global_step": 123, "final_loss": 0.31}


class _TrainerFailStub:
    def __init__(self, engine_id: str) -> None:
        self._engine_id = engine_id

    def train(self, dataset_path: str, resume_from=None):  # noqa: ANN001
        _ = dataset_path
        _ = resume_from
        adapter_dir = Path("tmp-adapters-fail") / self._engine_id
        adapter_dir.mkdir(parents=True, exist_ok=True)
        (adapter_dir / "adapter.bin").write_text("gpu-adapter", encoding="utf-8")
        return {"adapter_path": str(adapter_dir), "global_step": 321, "final_loss": 0.72}


class _OraclePassStub:
    def evaluate_artifact(self, request, validation_stage: str = ""):  # noqa: ANN001
        _ = request
        _ = validation_stage
        return Verdict(
            artifact_id="stage2",
            passed=True,
            score=0.93,
            reason="stage2-pass",
            criteria_scores={"overall": 0.93},
            evaluated_at="2026-04-24T00:00:00+00:00",
            oracle_mode="offline",
        )


class _OracleFailStub:
    def evaluate_artifact(self, request, validation_stage: str = ""):  # noqa: ANN001
        _ = request
        _ = validation_stage
        return Verdict(
            artifact_id="stage2",
            passed=False,
            score=0.21,
            reason="stage2-fail",
            criteria_scores={"overall": 0.21},
            evaluated_at="2026-04-24T00:00:00+00:00",
            oracle_mode="offline",
        )


def _write_config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "hybrid:",
                "  stage_pipeline:",
                "    cpu_cleared_prefix: training/stage1/cpu_cleared",
                "    artifact_prefix: training/artifacts",
                "    recycle_prefix: training/stage1/recycle",
            ]
        ),
        encoding="utf-8",
    )


def _write_gate(path: Path) -> None:
    path.write_text("promotion:\n  min_steps: 0\n", encoding="utf-8")


def _submit_cpu_cleared_job(orchestrator: HybridOrchestrator) -> str:
    return orchestrator.queue_cpu_cleared_adapter(
        engine_id="phi3",
        track="nato",
        cpu_adapter_key="training/stage1/cpu_cleared/nato/phi3/cpu.adapter.json",
        session_id="session-stage2",
        dataset_path="state/training/tracks/nato/scenarios",
        metadata={"cpu_step": 640},
    )


def test_stage2_promotes_to_artifact_vault_with_metadata(tmp_path: Path) -> None:
    config_path = tmp_path / "gpu_training.yaml"
    gate_path = tmp_path / "promotion_gate.yaml"
    _write_config(config_path)
    _write_gate(gate_path)

    connector = ObjectStorageConnector(emulation_root=tmp_path / "object-storage")
    orchestrator = HybridOrchestrator(
        queue_dir=str(tmp_path / "queue"),
        mode="gpu",
        config_path=str(config_path),
        oracle=_OraclePassStub(),
        object_storage_connector=connector,
        trainer_factory=lambda engine_id: _TrainerPassStub(engine_id),
    )
    orchestrator._promotion_gate = orchestrator._promotion_gate.__class__(config_path=gate_path)
    _submit_cpu_cleared_job(orchestrator)

    result = orchestrator.gpu_poll_and_run()
    assert result is not None
    assert result["stage2"]["promoted"] is True

    artifact_key = result["stage2"]["artifact_key"]
    metadata_key = result["stage2"]["metadata_key"]
    assert connector.exists(artifact_key)
    assert connector.exists(metadata_key)
    metadata = connector.get_json(metadata_key)
    assert metadata["track"] == "nato"
    assert metadata["engine"] == "phi3"
    assert metadata["session_id"] == "session-stage2"
    assert metadata["grok_score"] == pytest.approx(0.93)
    assert isinstance(metadata["timestamp"], str) and metadata["timestamp"]


def test_stage2_recycles_failed_adapters_with_feedback(tmp_path: Path) -> None:
    config_path = tmp_path / "gpu_training.yaml"
    gate_path = tmp_path / "promotion_gate.yaml"
    _write_config(config_path)
    _write_gate(gate_path)

    connector = ObjectStorageConnector(emulation_root=tmp_path / "object-storage")
    orchestrator = HybridOrchestrator(
        queue_dir=str(tmp_path / "queue"),
        mode="gpu",
        config_path=str(config_path),
        oracle=_OracleFailStub(),
        object_storage_connector=connector,
        trainer_factory=lambda engine_id: _TrainerFailStub(engine_id),
    )
    orchestrator._promotion_gate = orchestrator._promotion_gate.__class__(config_path=gate_path)
    _submit_cpu_cleared_job(orchestrator)

    result = orchestrator.gpu_poll_and_run()
    assert result is not None
    assert result["stage2"]["promoted"] is False
    feedback_key = result["stage2"]["recycle_feedback_key"]
    assert connector.exists(feedback_key)
    payload = connector.get_json(feedback_key)
    assert payload["status"] == "recycle_stage_1"
    assert payload["reason"] == "stage2-fail"

