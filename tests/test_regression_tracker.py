"""Unit tests for model regression tracking persistence and checks."""

from __future__ import annotations

import json

import pytest

from s3m_core.evaluation.regression_tracker import RegressionTracker


def test_record_persists_jsonl_and_supports_trend_queries(tmp_path) -> None:
    tracker = RegressionTracker(storage_dir=tmp_path / "tracker")
    tracker.record("v1", {"mission_success": 0.90, "latency_ms": 140.0})
    tracker.record("v2", {"mission_success": 0.95, "latency_ms": 130.0})

    trend = tracker.get_trend("mission_success", last_n_versions=5)
    assert trend == [("v1", 0.9), ("v2", 0.95)]

    jsonl_path = tmp_path / "tracker" / "jsonl_metrics" / "mission_success.jsonl"
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    record = json.loads(lines[-1])
    assert record["model_version"] == "v2"
    assert record["metric_value"] == 0.95


def test_check_regression_flags_degraded_metrics_with_severity(tmp_path) -> None:
    tracker = RegressionTracker(storage_dir=tmp_path / "tracker")
    tracker.record("baseline", {"mission_success": 0.90, "targeting_precision": 0.75})
    tracker.record("candidate", {"mission_success": 0.70, "targeting_precision": 0.73})

    regressions = tracker.check_regression("candidate", "baseline", threshold=0.05)

    assert len(regressions) == 1
    regression = regressions[0]
    assert regression.metric_name == "mission_success"
    assert regression.baseline_value == 0.90
    assert regression.new_value == 0.70
    assert regression.delta == -0.2
    assert regression.severity in {"high", "critical"}


def test_record_and_check_regression_validate_inputs(tmp_path) -> None:
    tracker = RegressionTracker(storage_dir=tmp_path / "tracker")

    with pytest.raises(ValueError):
        tracker.record("", {"metric": 1.0})
    with pytest.raises(ValueError):
        tracker.record("v1", {"metric": float("nan")})
    with pytest.raises(ValueError):
        tracker.check_regression("v2", "v1", threshold=-0.1)
