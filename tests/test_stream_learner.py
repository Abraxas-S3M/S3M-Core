"""Unit tests for StreamLearner CPU online adaptation."""

from __future__ import annotations

import pytest

from src.training.cpu_adaptation import StreamLearner


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
