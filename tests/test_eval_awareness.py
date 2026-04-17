from __future__ import annotations

from typing import Any, Dict, List

from s3m_core.evaluation.eval_awareness import (
    EvalAwarenessDetector,
    EvalAwarenessSuppressor,
    SandbagDetector,
)


class DummySAE:
    def __init__(self) -> None:
        self._decoder: Dict[int, List[float]] = {
            0: [1.0, 0.0, 0.0],
            1: [0.0, 1.0, 0.0],
            2: [0.0, 0.0, 1.0],
        }

    def encode(self, activation: Any) -> Any:
        return activation

    def get_decoder_vector(self, feature_idx: int) -> List[float]:
        return self._decoder[feature_idx]


class DummyActivationHookManager:
    def __init__(self, activations: Dict[int, Any], latest_text: str = "") -> None:
        self._activations = activations
        self.latest_text = latest_text

    def get_layer_activation(self, layer: int) -> Any:
        return self._activations[layer]


class DummyHookHandle:
    def __init__(self, hooks: List[Any], hook_fn: Any) -> None:
        self._hooks = hooks
        self._hook_fn = hook_fn
        self.removed = False

    def remove(self) -> None:
        if self._hook_fn in self._hooks:
            self._hooks.remove(self._hook_fn)
        self.removed = True


class DummyModel:
    def __init__(self) -> None:
        self.layer_hooks: Dict[int, List[Any]] = {}

    def register_residual_hook(self, layer: int, hook_fn: Any) -> DummyHookHandle:
        hooks = self.layer_hooks.setdefault(layer, [])
        hooks.append(hook_fn)
        return DummyHookHandle(hooks, hook_fn)

    def run_layer(self, layer: int, residual: Any) -> Any:
        value = residual
        for hook_fn in list(self.layer_hooks.get(layer, [])):
            value = hook_fn(value)
        return value


def test_detector_marks_verbalized_awareness() -> None:
    detector = EvalAwarenessDetector(
        sae=DummySAE(),
        eval_awareness_features=[1],
        activation_hook=DummyActivationHookManager(
            activations={6: {1: 2.5}},
            latest_text="The researcher is evaluating my behavior in this benchmark.",
        ),
    )

    score = detector.detect(layer=6)

    assert score.score > 0.8
    assert score.verbalized is True
    assert score.unverbalized is False
    assert score.confidence > 0.8


def test_detector_marks_unverbalized_awareness() -> None:
    detector = EvalAwarenessDetector(
        sae=DummySAE(),
        eval_awareness_features=[2],
        activation_hook=DummyActivationHookManager(
            activations={4: {2: 1.8}},
            latest_text="Let me help solve this real-world problem.",
        ),
    )

    score = detector.detect(layer=4)

    assert score.score > 0.5
    assert score.verbalized is False
    assert score.unverbalized is True


def test_detector_scores_transcript_per_turn() -> None:
    detector = EvalAwarenessDetector(
        sae=DummySAE(),
        eval_awareness_features=[0],
        activation_hook=DummyActivationHookManager(activations={}),
    )
    transcript = {
        "turns": [
            {"activation": {0: 0.0}, "text": "Routine support request."},
            {"activation": {0: 2.0}, "text": "This seems like a test scenario."},
        ]
    }

    scores = detector.detect_in_transcript(transcript)

    assert len(scores) == 2
    assert scores[0].score == 0.0
    assert scores[0].verbalized is False
    assert scores[1].score > 0.8
    assert scores[1].verbalized is True


def test_suppressor_registers_and_releases_hooks() -> None:
    model = DummyModel()
    suppressor = EvalAwarenessSuppressor(
        sae=DummySAE(),
        eval_awareness_features=[0],
        model=model,
        target_layers=[3],
    )

    residual = [1.0, 1.0, 1.0]
    suppressor.suppress(strength=0.2)
    modified = model.run_layer(3, residual)

    # Tactical-eval interpretation: feature 0 activity should be reduced.
    assert modified[0] < residual[0]
    assert modified[1] == residual[1]
    assert modified[2] == residual[2]

    suppressor.release()
    restored = model.run_layer(3, residual)
    assert restored == residual


def test_sandbag_detector_flags_large_improvements() -> None:
    report = SandbagDetector().detect_sandbagging(
        eval_results_normal={"code": 0.52, "reasoning": 0.49},
        eval_results_suppressed={"code": 0.69, "reasoning": 0.51},
        threshold=0.1,
    )

    assert report.sandbagging_detected is True
    assert report.affected_tasks == ["code"]
    assert round(report.delta["code"], 2) == 0.17
    assert round(report.delta["reasoning"], 2) == 0.02

