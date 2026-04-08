"""Unit tests for StreamLearner CPU online adaptation."""

from __future__ import annotations

import json

import pytest

from src.training.cpu_adaptation import StreamLearner
from src.training.cpu_adaptation.stream_learner import (
    log_embedding_training_sample,
    log_fleet_maintenance_training_sample,
)


def test_stream_learner_partial_fit_updates_samples() -> None:
    learner = StreamLearner(learning_rate=0.1, feature_dim=3)
    update = learner.partial_fit([1.0, 0.0, 0.0], target=1.0)
    assert update.samples_seen == 1
    assert learner.samples_seen == 1


def test_stream_learner_predict_and_state_dict() -> None:
    learner = StreamLearner(learning_rate=0.1)
    learner.partial_fit([1.0, 2.0], target=3.0)
    pred = learner.predict([1.0, 2.0])
    state = learner.state_dict()
    assert isinstance(pred, float)
    assert state["samples_seen"] == 1
    assert state["feature_dim"] == 2


def test_stream_learner_rejects_bad_input_shape() -> None:
    learner = StreamLearner(learning_rate=0.1, feature_dim=2)
    with pytest.raises(ValueError):
        learner.partial_fit([1.0], target=0.0)


def test_log_fleet_maintenance_training_sample_writes_jsonl(tmp_path) -> None:
    output = tmp_path / "fleet_maintenance.jsonl"
    payload = log_fleet_maintenance_training_sample(
        fleet_health={"units": [{"unitId": "alpha"}], "updatedAt": "2026-04-08T00:00:00+00:00"},
        maintenance_outcomes=[{"asset_id": "A1", "risk_level": "high"}],
        output_path=output,
    )
    assert output.exists()
    rows = output.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    stored = json.loads(rows[0])
    assert stored["fleetHealth"]["units"][0]["unitId"] == "alpha"
    assert stored["maintenanceOutcomes"][0]["asset_id"] == "A1"
    assert payload["maintenanceOutcomes"][0]["risk_level"] == "high"


def test_log_fleet_maintenance_training_sample_validates_inputs(tmp_path) -> None:
    output = tmp_path / "fleet_maintenance.jsonl"
    with pytest.raises(ValueError):
        log_fleet_maintenance_training_sample(
            fleet_health="bad",  # type: ignore[arg-type]
            output_path=output,
        )
    with pytest.raises(ValueError):
        log_fleet_maintenance_training_sample(
            maintenance_outcomes="bad",  # type: ignore[arg-type]
            output_path=output,
        )


def test_log_embedding_training_sample_writes_jsonl(tmp_path) -> None:
    output = tmp_path / "embedding_stream.jsonl"
    payload = log_embedding_training_sample(
        sample_id="concept-alpha",
        embedding=[0.1, 0.2, 0.3],
        metadata={"source": "semantic_memory", "priority": "high"},
        output_path=output,
    )
    assert output.exists()
    rows = output.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    stored = json.loads(rows[0])
    assert stored["sampleId"] == "concept-alpha"
    assert stored["metadata"]["source"] == "semantic_memory"
    assert abs(payload["embedding"][2] - 0.3) < 1e-6


def test_log_embedding_training_sample_validates_inputs(tmp_path) -> None:
    output = tmp_path / "embedding_stream.jsonl"
    with pytest.raises(ValueError):
        log_embedding_training_sample(
            sample_id="",
            embedding=[0.1, 0.2],
            output_path=output,
        )
    with pytest.raises(ValueError):
        log_embedding_training_sample(
            sample_id="ok",
            embedding=[],
            output_path=output,
        )
