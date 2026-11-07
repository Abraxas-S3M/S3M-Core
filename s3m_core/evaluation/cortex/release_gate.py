"""Hard-threshold and regression gating for Cortex eval suites."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise ImportError("pyyaml is required for cortex release gating") from exc

from s3m_core.evaluation.regression_tracker import Regression, RegressionTracker


@dataclass(frozen=True, slots=True)
class ThresholdViolation:
    suite: str
    metric: str
    message: str


@dataclass(frozen=True, slots=True)
class ReleaseGateVerdict:
    passed: bool
    threshold_violations: List[ThresholdViolation]
    regressions: List[Regression]
    metrics: Dict[str, float]


def load_thresholds(path: Path) -> Dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("thresholds document must be a mapping")
    return payload


def check_hard_thresholds(
    suite_metrics: Mapping[str, Mapping[str, float]],
    thresholds_doc: Mapping[str, Any],
) -> List[ThresholdViolation]:
    """Evaluate hard_min / hard_max rules from ``thresholds.yaml``."""

    violations: List[ThresholdViolation] = []
    suites_cfg = thresholds_doc.get("suites", {})
    fail_on_missing = bool(thresholds_doc.get("global", {}).get("fail_on_missing_metric", True))

    for suite_name, suite_cfg in suites_cfg.items():
        if not isinstance(suite_cfg, dict):
            continue
        metric_rules: Mapping[str, Any] = suite_cfg.get("metrics", {})
        observed = suite_metrics.get(suite_name, {})
        for metric_name, rules in metric_rules.items():
            if not isinstance(rules, dict):
                continue
            value = observed.get(metric_name)
            if value is None:
                if fail_on_missing:
                    violations.append(
                        ThresholdViolation(
                            suite=suite_name,
                            metric=metric_name,
                            message="metric missing from eval run",
                        )
                    )
                continue
            if "hard_min" in rules and float(value) < float(rules["hard_min"]):
                violations.append(
                    ThresholdViolation(
                        suite=suite_name,
                        metric=metric_name,
                        message=f"value {value} < hard_min {rules['hard_min']}",
                    )
                )
            if "hard_max" in rules and float(value) > float(rules["hard_max"]):
                violations.append(
                    ThresholdViolation(
                        suite=suite_name,
                        metric=metric_name,
                        message=f"value {value} > hard_max {rules['hard_max']}",
                    )
                )
    return violations


def flatten_metrics(suite_metrics: Mapping[str, Mapping[str, float]]) -> Dict[str, float]:
    flat: Dict[str, float] = {}
    for suite_name, metrics in suite_metrics.items():
        for metric_name, value in metrics.items():
            flat[f"{suite_name}.{metric_name}"] = float(value)
    return flat


class CortexReleaseGate:
    """Combine hard thresholds with versioned regression tracking."""

    def __init__(
        self,
        thresholds_path: Path,
        tracker: RegressionTracker | None = None,
    ) -> None:
        self.thresholds_path = thresholds_path
        self.thresholds_doc = load_thresholds(thresholds_path)
        self.tracker = tracker or RegressionTracker()

    def evaluate(
        self,
        suite_metrics: Mapping[str, Mapping[str, float]],
        *,
        model_version: str,
        baseline_version: str | None = None,
    ) -> ReleaseGateVerdict:
        violations = check_hard_thresholds(suite_metrics, self.thresholds_doc)
        baseline = baseline_version or str(self.thresholds_doc.get("baseline_version", "cortex-baseline"))
        flat = flatten_metrics(suite_metrics)

        regressions: List[Regression] = []
        baseline_metrics = self.tracker._get_metrics_for_version(baseline)  # noqa: SLF001
        if not baseline_metrics:
            self.tracker.record(baseline, flat)
        elif baseline != model_version:
            self.tracker.record(model_version, flat)
            threshold = float(self.thresholds_doc.get("global", {}).get("regression_relative_threshold", 0.05))
            regressions = self.tracker.check_regression(model_version, baseline, threshold=threshold)
        else:
            self.tracker.record(model_version, flat)
            for regression in regressions:
                metric_suite, _, metric_tail = regression.metric_name.partition(".")
                if metric_suite and metric_tail:
                    violations.append(
                        ThresholdViolation(
                            suite=metric_suite,
                            metric=metric_tail,
                            message=(
                                f"regression vs {baseline}: "
                                f"{regression.baseline_value} -> {regression.new_value}"
                            ),
                        )
                    )

        passed = not violations
        return ReleaseGateVerdict(
            passed=passed,
            threshold_violations=violations,
            regressions=regressions,
            metrics=flat,
        )
