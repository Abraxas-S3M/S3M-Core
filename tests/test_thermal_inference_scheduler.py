"""Unit tests for speculative thermal-aware inference scheduling."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.edge_runtime.thermal_inference_scheduler import (
    InferenceRequest,
    ThermalInferenceScheduler,
    ThermalModel,
)


def test_scheduler_disables_gracefully_when_no_sensor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ThermalInferenceScheduler,
        "_discover_thermal_sensors",
        lambda self: [],
    )
    scheduler = ThermalInferenceScheduler(profile=SimpleNamespace(cpu_cores=8), thermal_model=None)

    prediction = scheduler.schedule_request(
        InferenceRequest(request_id="r1", prompt_tokens=64, max_output_tokens=64),
        current_temp_c=52.0,
    )

    assert prediction.confidence == 0.0
    assert prediction.should_defer is False
    assert prediction.recommended_threads == 8
    assert prediction.recommended_cascade_level == "int8"
    assert scheduler.get_thermal_status()["enabled"] is False


def test_calibration_rejects_active_inference() -> None:
    scheduler = ThermalInferenceScheduler(profile=SimpleNamespace(cpu_cores=8, active_inference=True))
    with pytest.raises(RuntimeError, match="active inference"):
        scheduler.calibrate(duration_s=0.05)


def test_calibration_builds_model(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = ThermalInferenceScheduler(
        profile=SimpleNamespace(cpu_cores=8, ambient_temp_c=24.0, throttle_temp_c=96.0),
        thermal_model=None,
    )
    monkeypatch.setattr(scheduler, "_discover_thermal_sensors", lambda: [Path("/tmp/fake")])
    scheduler._sensor_paths = [Path("/tmp/fake")]

    readings = iter([40.0, 48.0, 44.0])
    monkeypatch.setattr(scheduler, "_read_current_temperature", lambda: next(readings))
    monkeypatch.setattr(scheduler, "_run_stress_test", lambda duration_s: None)
    monkeypatch.setattr("src.edge_runtime.thermal_inference_scheduler.time.sleep", lambda _: None)

    model = scheduler.calibrate(duration_s=0.05)
    assert model.thermal_capacitance > 0.0
    assert model.thermal_resistance > 0.0
    assert model.target_temp_c == 86.0
    assert scheduler._prediction_confidence() > 0.0


def test_schedule_downgrades_before_deferral() -> None:
    model = ThermalModel(
        thermal_capacitance=35.0,
        thermal_resistance=1.8,
        ambient_temp_c=25.0,
        throttle_temp_c=95.0,
        target_temp_c=55.0,
    )
    scheduler = ThermalInferenceScheduler(profile=SimpleNamespace(cpu_cores=16), thermal_model=model)
    request = InferenceRequest(
        request_id="r-hot",
        prompt_tokens=300,
        max_output_tokens=200,
        priority=2,
        min_cascade_level="ternary",
    )
    prediction = scheduler.schedule_request(request, current_temp_c=54.0)

    assert prediction.should_defer is False
    assert prediction.confidence > 0.0
    assert prediction.recommended_threads < 16 or prediction.recommended_cascade_level != "int8"


def test_schedule_defers_non_critical_only() -> None:
    model = ThermalModel(
        thermal_capacitance=30.0,
        thermal_resistance=1.6,
        ambient_temp_c=25.0,
        throttle_temp_c=95.0,
        target_temp_c=30.0,
    )
    scheduler = ThermalInferenceScheduler(profile=SimpleNamespace(cpu_cores=8), thermal_model=model)

    normal = scheduler.schedule_request(
        InferenceRequest(request_id="normal", prompt_tokens=512, max_output_tokens=512, priority=0),
        current_temp_c=39.0,
    )
    critical = scheduler.schedule_request(
        InferenceRequest(request_id="critical", prompt_tokens=512, max_output_tokens=512, priority=2),
        current_temp_c=39.0,
    )

    assert normal.should_defer is True
    assert critical.should_defer is False


def test_record_observation_adjusts_model_when_biased_hot() -> None:
    model = ThermalModel(
        thermal_capacitance=200.0,
        thermal_resistance=1.0,
        ambient_temp_c=25.0,
        throttle_temp_c=95.0,
        target_temp_c=85.0,
    )
    scheduler = ThermalInferenceScheduler(profile=SimpleNamespace(cpu_cores=8), thermal_model=model)
    initial_capacitance = scheduler.model.thermal_capacitance

    for idx in range(6):
        req_id = f"req-{idx}"
        prediction = scheduler.schedule_request(
            InferenceRequest(request_id=req_id, prompt_tokens=64, max_output_tokens=64),
            current_temp_c=50.0,
        )
        scheduler.record_observation(
            request_id=req_id,
            actual_temp_c=prediction.predicted_temp_c + 8.0,
            actual_duration_s=max(0.05, prediction.predicted_duration_s),
        )

    assert scheduler.model is not None
    assert scheduler.model.thermal_capacitance < initial_capacitance
