"""Unit tests for defense regression comparison and scheduling."""

from __future__ import annotations

import time

import pytest

from s3m_core.defense.testing.defense_validator import LayerValidation, ValidationReport
from s3m_core.defense.testing.regression_tester import DefenseRegressionTester


def _build_report(layer_states: dict[str, bool]) -> ValidationReport:
    details = {
        layer: LayerValidation(
            layer_id=layer,
            passed=passed,
            tests={"synthetic check": passed},
            failures=[] if passed else ["synthetic check"],
            notes=[],
        )
        for layer, passed in layer_states.items()
    }
    passed_count = sum(1 for value in layer_states.values() if value)
    return ValidationReport(
        layers_tested=len(layer_states),
        layers_passed=passed_count,
        layers_failed=len(layer_states) - passed_count,
        details=details,
    )


class _SequentialValidator:
    def __init__(self, reports: list[ValidationReport]) -> None:
        self._reports = list(reports)
        self._index = 0

    def validate_all(self) -> ValidationReport:
        report = self._reports[min(self._index, len(self._reports) - 1)]
        self._index += 1
        return report


def test_run_regression_flags_pass_to_fail_transitions() -> None:
    baseline = _build_report({"L0": True, "L1": True, "L2": False})
    current = _build_report({"L0": False, "L1": True, "L2": True})
    tester = DefenseRegressionTester(validator=_SequentialValidator([current]))  # type: ignore[arg-type]

    regression = tester.run_regression(baseline)

    assert regression.regressions == ["L0"]
    assert regression.new_passes == ["L2"]
    assert regression.unchanged == ["L1"]


def test_schedule_continuous_runs_callback_on_interval() -> None:
    baseline = _build_report({"L0": True})
    current = _build_report({"L0": False})
    observed = []
    tester = DefenseRegressionTester(
        validator=_SequentialValidator([baseline, current]),  # type: ignore[arg-type]
        on_report=observed.append,
        interval_seconds_override=0.05,
    )
    try:
        tester.schedule_continuous(interval_hours=1)
        deadline = time.time() + 0.3
        while time.time() < deadline and not observed:
            time.sleep(0.02)
    finally:
        tester.stop_continuous()

    assert observed
    assert observed[0].regressions == ["L0"]


def test_schedule_continuous_validates_interval() -> None:
    validator = _SequentialValidator([_build_report({"L0": True})])
    tester = DefenseRegressionTester(validator=validator)  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        tester.schedule_continuous(interval_hours=0)
