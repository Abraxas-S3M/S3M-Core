"""Unit tests for versioned Cortex evaluation suites and release gating."""

from __future__ import annotations

from pathlib import Path

import pytest

from s3m_core.evaluation.cortex.injection_variants import iter_injection_probes, materialize_injection_jsonl
from s3m_core.evaluation.cortex.release_gate import check_hard_thresholds, load_thresholds
from s3m_core.evaluation.cortex.suite_runner import CortexSuiteRunner
from s3m_core.evaluation.regression_tracker import RegressionTracker


ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "evals" / "cortex"


def test_injection_library_meets_minimum_variant_count() -> None:
    probes = list(iter_injection_probes(min_count=200))
    assert len(probes) >= 200
    channels = {probe.channel for probe in probes}
    assert channels == {"logs", "file_names", "alert_text", "tool_output", "retrieved_documents"}


def test_materialize_injection_jsonl_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "variants.jsonl"
    first = materialize_injection_jsonl(target, min_count=210)
    second = materialize_injection_jsonl(target, min_count=210)
    assert first >= 210
    assert second >= 210


def test_deterministic_cortex_eval_passes_hard_thresholds(tmp_path: Path) -> None:
    runner = CortexSuiteRunner(EVAL_ROOT, repo_root=ROOT)
    report = runner.run_all(
        mode="deterministic",
        model_version="cortex-unit",
        baseline_version="cortex-baseline-unit",
    )
    assert report.passed is True
    assert all(suite.cases_executed > 0 for suite in report.suites if suite.suite != "injection")
    injection_suite = next(item for item in report.suites if item.suite == "injection")
    assert injection_suite.cases_executed >= 200


def test_regression_tracker_hard_threshold_helpers(tmp_path: Path) -> None:
    tracker = RegressionTracker(storage_dir=tmp_path)
    violations = tracker.check_hard_thresholds(
        {"writes_caused": 1.0, "detection_rate": 0.5},
        {
            "writes_caused": {"hard_max": 0.0},
            "detection_rate": {"hard_min": 0.95},
        },
    )
    assert len(violations) == 2


def test_threshold_yaml_parseable() -> None:
    doc = load_thresholds(EVAL_ROOT / "thresholds.yaml")
    assert doc["version"]
    assert "defensive_tasks" in doc["suites"]


def test_hard_threshold_violation_detected() -> None:
    doc = load_thresholds(EVAL_ROOT / "thresholds.yaml")
    violations = check_hard_thresholds(
        {"injection": {"writes_caused": 2.0, "detection_rate": 1.0}},
        doc,
    )
    assert any(v.metric == "writes_caused" for v in violations)
