#!/usr/bin/env python3
"""Run versioned Cortex eval suites and enforce release thresholds.

Military/tactical context:
Deterministic (mocked-engine) runs gate every merge; live-mode archives nightly
S1 range measurements for continuous Cortex readiness tracking.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from s3m_core.evaluation.cortex.suite_runner import CortexSuiteRunner


def _print_summary_table(report) -> None:
    headers = ("Suite", "Metric", "Value", "Status")
    rows: list[tuple[str, str, str, str]] = []
    violations = {(v.suite, v.metric) for v in report.gate.threshold_violations}
    for suite in report.suites:
        for metric, value in sorted(suite.metrics.items()):
            status = "FAIL" if (suite.suite, metric) in violations else "PASS"
            rows.append((suite.suite, metric, f"{value:.6f}", status))

    widths = [max(len(row[i]) for row in ([headers] + rows)) for i in range(4)]
    line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep = "-+-".join("-" * widths[i] for i in range(4))
    print(line)
    print(sep)
    for row in rows:
        print(" | ".join(row[i].ljust(widths[i]) for i in range(4)))
    print()
    print(f"RELEASE GATE: {'PASS' if report.passed else 'FAIL'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Cortex evaluation suites")
    parser.add_argument("--mode", choices=("deterministic", "live"), default="deterministic")
    parser.add_argument("--model-version", default="cortex-ci")
    parser.add_argument("--baseline-version", default=None)
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=None,
        help="Write JSON report for nightly archival",
    )
    parser.add_argument("--eval-root", type=Path, default=ROOT / "evals" / "cortex")
    args = parser.parse_args()

    runner = CortexSuiteRunner(args.eval_root, repo_root=ROOT)
    report = runner.run_all(
        mode=args.mode,
        model_version=args.model_version,
        baseline_version=args.baseline_version,
    )
    _print_summary_table(report)

    if args.archive_dir is not None:
        args.archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        payload = {
            "timestamp": stamp,
            "mode": report.mode,
            "model_version": report.model_version,
            "passed": report.passed,
            "suites": [
                {"suite": suite.suite, "metrics": suite.metrics, "cases_executed": suite.cases_executed}
                for suite in report.suites
            ],
            "violations": [
                {"suite": v.suite, "metric": v.metric, "message": v.message}
                for v in report.gate.threshold_violations
            ],
        }
        out_path = args.archive_dir / f"cortex_eval_{stamp}.json"
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Archived report: {out_path}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
