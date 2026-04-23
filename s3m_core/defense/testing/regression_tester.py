"""Regression testing orchestration for defense validation outcomes.

Military/tactical context:
After software updates, regression checks ensure previously hardened defensive
layers remain effective before operational deployment.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable

from .defense_validator import DefenseValidator, ValidationReport


@dataclass(frozen=True, slots=True)
class RegressionReport:
    """Diff between baseline and current defense validation results."""

    regressions: list[str]
    new_passes: list[str]
    unchanged: list[str]


class DefenseRegressionTester:
    """Run defense validation repeatedly and flag pass-to-fail regressions."""

    def __init__(
        self,
        validator: DefenseValidator,
        on_report: Callable[[RegressionReport], None] | None = None,
        interval_seconds_override: float | None = None,
    ) -> None:
        self._validator = validator
        self._on_report = on_report
        self._interval_seconds_override = interval_seconds_override
        self._scheduler_stop = threading.Event()
        self._scheduler_thread: threading.Thread | None = None

    def run_regression(self, baseline: ValidationReport) -> RegressionReport:
        """Compare current validation against baseline and classify deltas."""

        if not isinstance(baseline, ValidationReport):
            raise ValueError("baseline must be a ValidationReport instance")

        current = self._validator.validate_all()
        all_layers = sorted(set(baseline.details).union(current.details))
        regressions: list[str] = []
        new_passes: list[str] = []
        unchanged: list[str] = []

        for layer in all_layers:
            baseline_passed = baseline.details.get(layer).passed if layer in baseline.details else False
            current_passed = current.details.get(layer).passed if layer in current.details else False
            if baseline_passed and not current_passed:
                regressions.append(layer)
            elif not baseline_passed and current_passed:
                new_passes.append(layer)
            else:
                unchanged.append(layer)

        return RegressionReport(regressions=regressions, new_passes=new_passes, unchanged=unchanged)

    def schedule_continuous(self, interval_hours: int = 24) -> None:
        """Run regression checks on a continuous schedule."""

        if not isinstance(interval_hours, int) or interval_hours <= 0:
            raise ValueError("interval_hours must be a positive integer")
        if self._scheduler_thread is not None and self._scheduler_thread.is_alive():
            return

        baseline = self._validator.validate_all()
        interval_seconds = float(interval_hours * 3600)
        if self._interval_seconds_override is not None:
            interval_seconds = float(self._interval_seconds_override)

        self._scheduler_stop.clear()
        self._scheduler_thread = threading.Thread(
            target=self._continuous_loop,
            args=(baseline, interval_seconds),
            daemon=True,
            name="s3m-defense-regression-scheduler",
        )
        self._scheduler_thread.start()

    def stop_continuous(self) -> None:
        """Stop background regression scheduling."""

        self._scheduler_stop.set()
        if self._scheduler_thread is not None:
            self._scheduler_thread.join(timeout=0.5)
        self._scheduler_thread = None

    def _continuous_loop(self, baseline: ValidationReport, interval_seconds: float) -> None:
        while not self._scheduler_stop.wait(interval_seconds):
            report = self.run_regression(baseline)
            if self._on_report is not None:
                self._on_report(report)
