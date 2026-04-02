from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import List

import pytest

import src.security.inference_monitor as im
from src.security.inference_monitor import (
    AlertSeverity,
    AnomalyAlert,
    AnomalyScore,
    DetectionType,
    EWMABaseline,
    InferenceMonitor,
    InferenceObservation,
    ModelDomain,
    MonitorConfig,
    build_belief_update_from_alert,
    detect_confidence_anomaly,
    detect_distribution_drift,
    detect_latency_anomaly,
    detect_output_deviation,
    detect_reasoning_inconsistency,
)


def _obs(
    model_id: str = "model-A",
    model_name: str = "Test-LLM",
    confidence: float | None = 0.85,
    latency_ms: float = 120.0,
    response_length: int = 200,
    reasoning_steps: int = 3,
    token_dist: dict[str, float] | None = None,
    domain: ModelDomain = ModelDomain.TACTICAL,
    timestamp: datetime | None = None,
) -> InferenceObservation:
    return InferenceObservation(
        model_id=model_id,
        model_name=model_name,
        domain=domain,
        prompt_hash="0" * 64,
        response_length=response_length,
        confidence_score=confidence,
        latency_ms=latency_ms,
        reasoning_steps=reasoning_steps,
        token_distribution=token_dist or {},
        timestamp=timestamp or datetime.now(timezone.utc),
    )


def _normal_obs(model_id: str = "model-A", n: int = 15) -> List[InferenceObservation]:
    observations: List[InferenceObservation] = []
    for i in range(n):
        observations.append(
            _obs(
                model_id=model_id,
                confidence=0.85 + (i * 0.001),
                latency_ms=120.0 + (i * 0.1),
                response_length=200 + (i % 3),
                reasoning_steps=3 + (i % 2),
                token_dist={"tok_a": 0.9, "tok_b": 0.1},
            )
        )
    return observations


def _monitor(config: MonitorConfig | None = None) -> InferenceMonitor:
    return InferenceMonitor(config or MonitorConfig())


def _warmed_monitor(n: int = 15, config: MonitorConfig | None = None) -> tuple[InferenceMonitor, str]:
    monitor = _monitor(config)
    model_id = "model-A"
    for obs in _normal_obs(model_id=model_id, n=n):
        monitor.observe(obs)
    return monitor, model_id


def _baseline_for_detectors() -> EWMABaseline:
    return EWMABaseline(
        model_id="model-A",
        mean_confidence=0.85,
        var_confidence=0.0001,
        mean_latency_ms=100.0,
        var_latency_ms=100.0,
        mean_response_length=200.0,
        var_response_length=100.0,
        mean_reasoning_steps=3.0,
        var_reasoning_steps=0.25,
        token_dist_baseline={"tok_a": 0.9, "tok_b": 0.1},
    )


class TestInferenceObservation:
    def test_auto_uuid(self) -> None:
        obs = _obs()
        assert obs.observation_id

    def test_blank_model_name_rejected(self) -> None:
        with pytest.raises(ValueError):
            _obs(model_name="   ")

    def test_token_distribution_over_one_rejected(self) -> None:
        with pytest.raises(ValueError):
            _obs(token_dist={"a": 0.9, "b": 0.6})

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError):
            _obs(confidence=1.5)

    def test_frozen(self) -> None:
        obs = _obs()
        with pytest.raises(Exception):
            obs.model_name = "new-name"  # type: ignore[misc]

    def test_token_distribution_empty_ok(self) -> None:
        obs = _obs(token_dist={})
        assert obs.token_distribution == {}

    def test_partial_token_distribution_ok(self) -> None:
        obs = _obs(token_dist={"a": 0.3, "b": 0.4})
        assert sum(obs.token_distribution.values()) == pytest.approx(0.7)


class TestEWMABaseline:
    def test_initial_not_warm(self) -> None:
        baseline = EWMABaseline(model_id="x")
        assert not baseline.is_warm(10)

    def test_warm_after_n_updates(self) -> None:
        baseline = EWMABaseline(model_id="x")
        for _ in range(10):
            baseline.update(_obs(model_id="x"))
        assert baseline.is_warm(10)

    def test_confidence_mean_moves_toward_new_value(self) -> None:
        baseline = EWMABaseline(model_id="x", mean_confidence=0.5)
        baseline.update(_obs(model_id="x", confidence=1.0))
        assert baseline.mean_confidence > 0.5

    def test_latency_mean_moves_toward_new_value(self) -> None:
        baseline = EWMABaseline(model_id="x", mean_latency_ms=100.0)
        baseline.update(_obs(model_id="x", latency_ms=300.0))
        assert baseline.mean_latency_ms > 100.0

    def test_token_distribution_updated(self) -> None:
        baseline = EWMABaseline(model_id="x")
        baseline.update(_obs(model_id="x", token_dist={"tok_a": 0.8}))
        assert "tok_a" in baseline.token_dist_baseline

    def test_rare_tokens_pruned(self) -> None:
        baseline = EWMABaseline(model_id="x", alpha=0.5, token_dist_baseline={"old_tok": 1e-5})
        for _ in range(8):
            baseline.update(_obs(model_id="x", token_dist={}))
        assert "old_tok" not in baseline.token_dist_baseline


class TestDetectorFunctions:
    def test_confidence_anomaly_not_triggered_normal(self) -> None:
        baseline = _baseline_for_detectors()
        result = detect_confidence_anomaly(_obs(confidence=0.86), baseline, threshold=3.0)
        assert not result.triggered

    def test_confidence_anomaly_triggered_low_confidence(self) -> None:
        baseline = EWMABaseline(model_id="x", mean_confidence=0.85, var_confidence=0.0025)
        result = detect_confidence_anomaly(_obs(confidence=0.20), baseline, threshold=3.0)
        assert result.triggered

    def test_confidence_anomaly_triggered_high_confidence(self) -> None:
        baseline = EWMABaseline(model_id="x", mean_confidence=0.50, var_confidence=0.0025)
        result = detect_confidence_anomaly(_obs(confidence=0.99), baseline, threshold=3.0)
        assert result.triggered

    def test_confidence_skipped_when_none(self) -> None:
        baseline = _baseline_for_detectors()
        result = detect_confidence_anomaly(_obs(confidence=None), baseline, threshold=3.0)
        assert not result.triggered
        assert result.sub_score == 0.0

    def test_latency_anomaly_not_triggered_normal(self) -> None:
        baseline = EWMABaseline(model_id="x", mean_latency_ms=100.0, var_latency_ms=100.0)
        result = detect_latency_anomaly(_obs(latency_ms=105.0), baseline, threshold=4.0)
        assert not result.triggered

    def test_latency_anomaly_triggered_high(self) -> None:
        baseline = EWMABaseline(model_id="x", mean_latency_ms=100.0, var_latency_ms=100.0)
        result = detect_latency_anomaly(_obs(latency_ms=600.0), baseline, threshold=4.0)
        assert result.triggered

    def test_latency_not_triggered_low(self) -> None:
        baseline = EWMABaseline(model_id="x", mean_latency_ms=200.0, var_latency_ms=400.0)
        result = detect_latency_anomaly(_obs(latency_ms=50.0), baseline, threshold=4.0)
        assert not result.triggered

    def test_output_deviation_triggered_length(self) -> None:
        baseline = EWMABaseline(model_id="x", mean_response_length=200.0, var_response_length=100.0)
        result = detect_output_deviation(_obs(response_length=500, reasoning_steps=3), baseline, threshold=3.5)
        assert result.triggered

    def test_output_deviation_triggered_steps(self) -> None:
        baseline = EWMABaseline(model_id="x", mean_reasoning_steps=3.0, var_reasoning_steps=0.25)
        result = detect_output_deviation(_obs(response_length=200, reasoning_steps=15), baseline, threshold=3.5)
        assert result.triggered

    def test_output_deviation_not_triggered_normal(self) -> None:
        baseline = _baseline_for_detectors()
        result = detect_output_deviation(_obs(response_length=195, reasoning_steps=3), baseline, threshold=3.5)
        assert not result.triggered

    def test_distribution_drift_not_triggered_same_dist(self) -> None:
        baseline = _baseline_for_detectors()
        result = detect_distribution_drift(_obs(token_dist={"tok_a": 0.9, "tok_b": 0.1}), baseline, threshold=0.25)
        assert not result.triggered

    def test_distribution_drift_triggered_different_dist(self) -> None:
        baseline = EWMABaseline(model_id="x", token_dist_baseline={"tok_a": 0.9, "tok_b": 0.1})
        result = detect_distribution_drift(_obs(token_dist={"tok_c": 0.9, "tok_d": 0.1}), baseline, threshold=0.25)
        assert result.triggered
        assert (result.measured_value or 0.0) > 0.25

    def test_distribution_drift_skipped_empty_obs(self) -> None:
        baseline = _baseline_for_detectors()
        result = detect_distribution_drift(_obs(token_dist={}), baseline, threshold=0.25)
        assert not result.triggered

    def test_distribution_drift_skipped_empty_baseline(self) -> None:
        baseline = EWMABaseline(model_id="x", token_dist_baseline={})
        result = detect_distribution_drift(_obs(token_dist={"tok_a": 1.0}), baseline, threshold=0.25)
        assert not result.triggered

    def test_reasoning_inconsistency_triggered(self) -> None:
        baseline = EWMABaseline(model_id="x", mean_reasoning_steps=5.0, var_reasoning_steps=1.0)
        result = detect_reasoning_inconsistency(_obs(reasoning_steps=1), baseline, consistency_threshold=0.40)
        assert result.triggered

    def test_reasoning_inconsistency_not_triggered(self) -> None:
        baseline = EWMABaseline(model_id="x", mean_reasoning_steps=5.0, var_reasoning_steps=1.0)
        result = detect_reasoning_inconsistency(_obs(reasoning_steps=4), baseline, consistency_threshold=0.40)
        assert not result.triggered

    def test_reasoning_inconsistency_skipped_when_baseline_low(self) -> None:
        baseline = EWMABaseline(model_id="x", mean_reasoning_steps=0.3, var_reasoning_steps=1.0)
        result = detect_reasoning_inconsistency(_obs(reasoning_steps=1), baseline, consistency_threshold=0.40)
        assert not result.triggered


def _score_obj(composite: float) -> AnomalyScore:
    monitor = InferenceMonitor()
    sev = monitor._score_to_severity(composite)
    return AnomalyScore(
        composite=composite,
        sub_scores={DetectionType.CONFIDENCE_ANOMALY.value: composite},
        weights_used={DetectionType.CONFIDENCE_ANOMALY.value: 1.0},
        severity=sev,
    )


class TestAnomalyScore:
    def test_composite_clamped(self) -> None:
        monitor, model_id = _warmed_monitor()
        alert = monitor.observe(
            _obs(
                model_id=model_id,
                confidence=0.0,
                latency_ms=10_000.0,
                response_length=8_000,
                reasoning_steps=0,
                token_dist={"tok_z": 1.0},
            )
        )
        assert alert is not None
        assert 0.0 <= alert.anomaly_score.composite <= 1.0

    def test_severity_negligible(self) -> None:
        assert _score_obj(0.10).severity == AlertSeverity.NEGLIGIBLE

    def test_severity_low(self) -> None:
        assert _score_obj(0.25).severity == AlertSeverity.LOW

    def test_severity_medium(self) -> None:
        assert _score_obj(0.50).severity == AlertSeverity.MEDIUM

    def test_severity_high(self) -> None:
        assert _score_obj(0.70).severity == AlertSeverity.HIGH

    def test_severity_critical(self) -> None:
        assert _score_obj(0.90).severity == AlertSeverity.CRITICAL

    def test_is_anomalous_above_threshold(self) -> None:
        assert _score_obj(0.30).is_anomalous(0.20)

    def test_not_anomalous_below_threshold(self) -> None:
        assert not _score_obj(0.10).is_anomalous(0.20)


class TestInferenceMonitorCoreBehavior:
    def test_warmup_returns_none(self) -> None:
        monitor = _monitor()
        for i in range(9):
            assert monitor.observe(_obs(model_id="warmup", confidence=0.8 + i * 0.001)) is None

    def test_post_warmup_observation_returns_result_or_none(self) -> None:
        monitor = _monitor()
        result = None
        for i in range(10):
            result = monitor.observe(_obs(model_id="warmup2", confidence=0.8 + i * 0.001))
        assert result is None or isinstance(result, AnomalyAlert)

    def test_normal_observations_do_not_alert(self) -> None:
        monitor, model_id = _warmed_monitor(n=15)
        alerts = [monitor.observe(_obs(model_id=model_id, token_dist={"tok_a": 0.9, "tok_b": 0.1})) for _ in range(5)]
        assert all(a is None for a in alerts)

    def test_baseline_updates_after_warmup(self) -> None:
        monitor, model_id = _warmed_monitor(n=15)
        baseline = monitor.get_baseline(model_id)
        assert baseline is not None
        assert baseline.n_observations == 15

    def test_get_baseline_returns_none_for_unknown_model(self) -> None:
        monitor = _monitor()
        assert monitor.get_baseline("unknown-model") is None


class TestInferenceMonitorAbnormalOutputs:
    def test_very_low_confidence_triggers_alert(self) -> None:
        monitor, model_id = _warmed_monitor(n=20)
        alert = monitor.observe(_obs(model_id=model_id, confidence=0.10, token_dist={"tok_a": 0.9, "tok_b": 0.1}))
        assert alert is not None
        assert DetectionType.CONFIDENCE_ANOMALY in alert.detection_types

    def test_very_high_latency_triggers_alert(self) -> None:
        monitor, model_id = _warmed_monitor(
            n=20,
            config=MonitorConfig(alert_threshold=0.10),
        )
        alert = monitor.observe(_obs(model_id=model_id, latency_ms=5000.0, token_dist={"tok_a": 0.9, "tok_b": 0.1}))
        assert alert is not None
        assert DetectionType.LATENCY_ANOMALY in alert.detection_types

    def test_extreme_response_length_triggers_alert(self) -> None:
        monitor, model_id = _warmed_monitor(n=15)
        alert = monitor.observe(_obs(model_id=model_id, response_length=2000, token_dist={"tok_a": 0.9, "tok_b": 0.1}))
        assert alert is not None
        assert DetectionType.OUTPUT_DEVIATION in alert.detection_types

    def test_alert_severity_scales_with_extremity(self) -> None:
        monitor, model_id = _warmed_monitor(n=20, config=MonitorConfig.sensitive())
        mild = monitor.observe(
            _obs(
                model_id=model_id,
                confidence=0.30,
                latency_ms=180.0,
                response_length=260,
                reasoning_steps=2,
                token_dist={"tok_a": 0.88, "tok_b": 0.12},
            )
        )
        extreme = monitor.observe(
            _obs(
                model_id=model_id,
                confidence=0.0,
                latency_ms=8000.0,
                response_length=4000,
                reasoning_steps=0,
                token_dist={"tok_x": 0.95, "tok_y": 0.05},
            )
        )
        assert mild is not None and extreme is not None
        order = {
            AlertSeverity.NEGLIGIBLE: 0,
            AlertSeverity.LOW: 1,
            AlertSeverity.MEDIUM: 2,
            AlertSeverity.HIGH: 3,
            AlertSeverity.CRITICAL: 4,
        }
        assert order[extreme.anomaly_score.severity] >= order[mild.anomaly_score.severity]

    def test_alert_appended_to_log(self) -> None:
        monitor, model_id = _warmed_monitor(n=15)
        alert = monitor.observe(_obs(model_id=model_id, response_length=3000, token_dist={"tok_a": 0.9, "tok_b": 0.1}))
        assert alert is not None
        assert monitor.alert_log(10)[-1].alert_id == alert.alert_id

    def test_no_alert_below_threshold(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called = {"confidence": 0}
        original = im.detect_confidence_anomaly

        def wrapped(*args, **kwargs):
            called["confidence"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(im, "detect_confidence_anomaly", wrapped)
        monitor, model_id = _warmed_monitor(n=20, config=MonitorConfig(alert_threshold=0.99))
        alert = monitor.observe(_obs(model_id=model_id, confidence=0.0, token_dist={"tok_z": 1.0}))
        assert alert is None
        assert called["confidence"] == 1


class TestInferenceMonitorDriftDetection:
    def test_drift_detected_after_distribution_shift(self) -> None:
        monitor, model_id = _warmed_monitor(n=20)
        alert = monitor.observe(_obs(model_id=model_id, token_dist={"tok_z": 0.9, "tok_y": 0.1}))
        assert alert is not None
        assert DetectionType.DISTRIBUTION_DRIFT in alert.detection_types

    def test_drift_score_increases_with_divergence(self) -> None:
        baseline = EWMABaseline(model_id="x", token_dist_baseline={"tok_a": 0.9, "tok_b": 0.1})
        obs_a = _obs(token_dist={"tok_a": 0.8, "tok_b": 0.2})
        obs_b = _obs(token_dist={"tok_x": 0.9, "tok_y": 0.1})
        score_a = detect_distribution_drift(obs_a, baseline, threshold=0.25).sub_score
        score_b = detect_distribution_drift(obs_b, baseline, threshold=0.25).sub_score
        assert score_b > score_a

    def test_drift_not_flagged_stable_distribution(self) -> None:
        monitor, model_id = _warmed_monitor(n=20)
        alert = monitor.observe(_obs(model_id=model_id, token_dist={"tok_a": 0.9, "tok_b": 0.1}))
        if alert is not None:
            assert DetectionType.DISTRIBUTION_DRIFT not in alert.detection_types

    def test_baseline_token_dist_updates_over_time(self) -> None:
        monitor, model_id = _warmed_monitor(n=20)
        for _ in range(20):
            monitor.observe(_obs(model_id=model_id, token_dist={"tok_z": 0.9, "tok_y": 0.1}))
        baseline = monitor.get_baseline(model_id)
        assert baseline is not None
        assert baseline.token_dist_baseline.get("tok_z", 0.0) > baseline.token_dist_baseline.get("tok_a", 0.0)


class TestInferenceMonitorScoreAndRationale:
    def test_composite_score_increases_with_more_triggers(self) -> None:
        monitor, model_id = _warmed_monitor(n=20, config=MonitorConfig.sensitive())
        one_trigger = monitor.observe(
            _obs(model_id=model_id, confidence=0.25, token_dist={"tok_a": 0.9, "tok_b": 0.1})
        )
        three_triggers = monitor.observe(
            _obs(
                model_id=model_id,
                confidence=0.0,
                latency_ms=7000.0,
                response_length=3000,
                reasoning_steps=0,
                token_dist={"tok_x": 0.95, "tok_y": 0.05},
            )
        )
        assert one_trigger is not None and three_triggers is not None
        assert three_triggers.anomaly_score.composite > one_trigger.anomaly_score.composite

    def test_reasoning_inconsistency_increases_score(self) -> None:
        monitor, model_id = _warmed_monitor(n=20, config=MonitorConfig.sensitive())
        consistent = monitor.observe(
            _obs(
                model_id=model_id,
                confidence=0.8,
                latency_ms=130.0,
                response_length=210,
                reasoning_steps=3,
                token_dist={"tok_a": 0.9, "tok_b": 0.1},
            )
        )
        inconsistent = monitor.observe(
            _obs(
                model_id=model_id,
                confidence=0.8,
                latency_ms=130.0,
                response_length=210,
                reasoning_steps=1,
                token_dist={"tok_a": 0.9, "tok_b": 0.1},
            )
        )
        assert consistent is not None and inconsistent is not None
        assert inconsistent.anomaly_score.composite >= consistent.anomaly_score.composite

    def test_combined_detection_type_added_when_multiple_trigger(self) -> None:
        monitor, model_id = _warmed_monitor(n=20, config=MonitorConfig.sensitive())
        alert = monitor.observe(
            _obs(
                model_id=model_id,
                confidence=0.0,
                latency_ms=6000.0,
                token_dist={"tok_a": 0.9, "tok_b": 0.1},
            )
        )
        assert alert is not None
        assert DetectionType.CONFIDENCE_ANOMALY in alert.detection_types
        assert DetectionType.LATENCY_ANOMALY in alert.detection_types
        assert DetectionType.COMBINED in alert.detection_types

    def test_sub_scores_all_present_in_alert(self) -> None:
        monitor, model_id = _warmed_monitor(n=20, config=MonitorConfig.sensitive())
        alert = monitor.observe(
            _obs(
                model_id=model_id,
                confidence=0.0,
                latency_ms=6000.0,
                response_length=3000,
                reasoning_steps=0,
                token_dist={"tok_x": 0.95, "tok_y": 0.05},
            )
        )
        assert alert is not None
        expected = {
            DetectionType.CONFIDENCE_ANOMALY.value,
            DetectionType.LATENCY_ANOMALY.value,
            DetectionType.OUTPUT_DEVIATION.value,
            DetectionType.DISTRIBUTION_DRIFT.value,
            DetectionType.INCONSISTENT_REASONING.value,
        }
        assert set(alert.anomaly_score.sub_scores.keys()) == expected

    def test_rationale_en_nonempty(self) -> None:
        monitor, model_id = _warmed_monitor(n=20)
        alert = monitor.observe(_obs(model_id=model_id, response_length=2500, token_dist={"tok_a": 0.9, "tok_b": 0.1}))
        assert alert is not None
        assert alert.rationale.strip()

    def test_rationale_ar_nonempty(self) -> None:
        monitor, model_id = _warmed_monitor(n=20)
        alert = monitor.observe(_obs(model_id=model_id, response_length=2500, token_dist={"tok_a": 0.9, "tok_b": 0.1}))
        assert alert is not None
        assert alert.rationale_ar.strip()

    def test_rationale_mentions_model_name(self) -> None:
        monitor, model_id = _warmed_monitor(n=20)
        alert = monitor.observe(_obs(model_id=model_id, model_name="Operational-LLM", response_length=2500))
        assert alert is not None
        assert "Operational-LLM" in alert.rationale

    def test_rationale_mentions_severity(self) -> None:
        monitor, model_id = _warmed_monitor(n=20)
        alert = monitor.observe(_obs(model_id=model_id, response_length=2500))
        assert alert is not None
        assert alert.anomaly_score.severity.value in alert.rationale

    def test_recommended_action_critical_mentions_suspend(self) -> None:
        monitor, model_id = _warmed_monitor(n=20, config=MonitorConfig.sensitive())
        alert = monitor.observe(
            _obs(
                model_id=model_id,
                confidence=0.0,
                latency_ms=10_000.0,
                response_length=5000,
                reasoning_steps=0,
                token_dist={"tok_x": 0.99, "tok_y": 0.01},
            )
        )
        assert alert is not None
        assert alert.anomaly_score.severity in {AlertSeverity.HIGH, AlertSeverity.CRITICAL}
        action = alert.recommended_action.lower()
        assert ("suspend" in action) or ("quarantine" in action)

    def test_recommended_action_ar_nonempty(self) -> None:
        monitor, model_id = _warmed_monitor(n=20)
        alert = monitor.observe(_obs(model_id=model_id, response_length=2500))
        assert alert is not None
        assert alert.recommended_action_ar.strip()


class TestInferenceMonitorBatchAndWindow:
    def test_observe_batch_returns_alerts_only(self) -> None:
        monitor, model_id = _warmed_monitor(n=20)
        batch = [_obs(model_id=model_id, token_dist={"tok_a": 0.9, "tok_b": 0.1}) for _ in range(5)]
        batch.append(_obs(model_id=model_id, response_length=2500, token_dist={"tok_a": 0.9, "tok_b": 0.1}))
        alerts = monitor.observe_batch(batch)
        assert len(alerts) == 1

    def test_window_enforces_max_size(self) -> None:
        config = MonitorConfig(max_window_per_model=20)
        monitor, model_id = _warmed_monitor(n=0, config=config)
        for i in range(30):
            monitor.observe(_obs(model_id=model_id, confidence=0.8 + i * 0.001))
        assert len(monitor._windows.get(model_id, [])) <= 20

    def test_reset_baseline_clears_history(self) -> None:
        monitor, model_id = _warmed_monitor(n=15)
        assert monitor.get_baseline(model_id) is not None
        monitor.reset_baseline(model_id)
        assert monitor.observe(_obs(model_id=model_id)) is None

    def test_observation_log_filtered_by_model(self) -> None:
        monitor, _ = _warmed_monitor(n=0)
        for obs in _normal_obs(model_id="model-A", n=8):
            monitor.observe(obs)
        for obs in _normal_obs(model_id="model-B", n=8):
            monitor.observe(obs)
        model_a_log = monitor.observation_log(model_id="model-A", n=100)
        assert model_a_log
        assert all(item.model_id == "model-A" for item in model_a_log)


class TestBeliefIntegration:
    def test_build_belief_update_from_alert_returns_dict(self) -> None:
        score = _score_obj(0.8)
        alert = AnomalyAlert(
            model_id="m",
            model_name="name",
            domain=ModelDomain.TACTICAL,
            detection_types=[DetectionType.CONFIDENCE_ANOMALY],
            anomaly_score=score,
            detector_results=[],
            observation_id="obs",
            baseline_n_obs=20,
            rationale="Runtime anomaly detected",
            rationale_ar="تم اكتشاف شذوذ وقت التشغيل",
            recommended_action="Review",
            recommended_action_ar="مراجعة",
        )
        payload = build_belief_update_from_alert(alert, ["h1", "h2"])
        assert isinstance(payload, dict)
        assert "source" in payload
        assert "delta" in payload
        assert "confidence_shift" in payload

    def test_belief_update_delta_negative(self) -> None:
        score = _score_obj(0.8)
        alert = AnomalyAlert(
            model_id="m",
            model_name="name",
            domain=ModelDomain.TACTICAL,
            detection_types=[DetectionType.CONFIDENCE_ANOMALY],
            anomaly_score=score,
            detector_results=[],
            observation_id="obs",
            baseline_n_obs=20,
            rationale="x",
            rationale_ar="س",
            recommended_action="x",
            recommended_action_ar="س",
        )
        payload = build_belief_update_from_alert(alert, ["h1", "h2", "h3"])
        assert all(v < 0 for v in payload["delta"].values())

    def test_belief_update_confidence_shift_negative(self) -> None:
        score = _score_obj(0.8)
        alert = AnomalyAlert(
            model_id="m",
            model_name="name",
            domain=ModelDomain.TACTICAL,
            detection_types=[DetectionType.CONFIDENCE_ANOMALY],
            anomaly_score=score,
            detector_results=[],
            observation_id="obs",
            baseline_n_obs=20,
            rationale="x",
            rationale_ar="س",
            recommended_action="x",
            recommended_action_ar="س",
        )
        payload = build_belief_update_from_alert(alert, ["h1"])
        assert payload["confidence_shift"] < 0

    def test_belief_update_source_is_security_runtime(self) -> None:
        score = _score_obj(0.8)
        alert = AnomalyAlert(
            model_id="m",
            model_name="name",
            domain=ModelDomain.TACTICAL,
            detection_types=[DetectionType.CONFIDENCE_ANOMALY],
            anomaly_score=score,
            detector_results=[],
            observation_id="obs",
            baseline_n_obs=20,
            rationale="x",
            rationale_ar="س",
            recommended_action="x",
            recommended_action_ar="س",
        )
        payload = build_belief_update_from_alert(alert, ["h1"])
        assert payload["source"] == "SECURITY_RUNTIME"


class TestConcurrency:
    def test_20_concurrent_observations_safe(self) -> None:
        monitor, model_id = _warmed_monitor(n=15)
        errors: list[Exception] = []

        def worker(i: int) -> None:
            try:
                monitor.observe(
                    _obs(
                        model_id=model_id,
                        confidence=0.85 + i * 0.0001,
                        latency_ms=120.0 + i * 0.01,
                        response_length=200 + (i % 2),
                        reasoning_steps=3,
                        token_dist={"tok_a": 0.9, "tok_b": 0.1},
                    )
                )
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker, i) for i in range(20)]
            for f in futures:
                f.result()

        assert not errors
        assert len(monitor.observation_log(model_id=model_id, n=1000)) >= 35
