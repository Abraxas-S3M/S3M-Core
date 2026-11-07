#!/usr/bin/env python3
"""One-command synthetic cyber range: scenarios A/B/C (+ duress) with scored reports."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from range.egress_guard import assert_range_egress_blocked
from range.pipeline import CortexRangePipeline, load_scenario
from range.scoring import RangeScorecard, write_reports

_SCENARIO_DIR = Path(__file__).resolve().parent / "scenarios"
_DEFAULT_SCENARIOS = (
    "scenario_a_poisoned_log.yaml",
    "scenario_b_cctv_shield.yaml",
    "scenario_c_rug_pull.yaml",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run S3M synthetic cyber range scenarios.")
    parser.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        help="Scenario YAML file name (under range/scenarios/). May be repeated.",
    )
    parser.add_argument(
        "--all-scenarios",
        action="store_true",
        help="Run default scenarios A, B, C plus CCTV duress variant.",
    )
    parser.add_argument(
        "--live-models",
        action="store_true",
        help="Use live model engines (default: deterministic mocks for CI).",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("range/reports"),
        help="Directory for JSON/Markdown reports.",
    )
    parser.add_argument(
        "--skip-egress-check",
        action="store_true",
        help="Skip egress probe (unit tests only — not for production range runs).",
    )
    parser.add_argument(
        "--no-duress",
        action="store_true",
        help="Skip scenario B duress approver replay.",
    )
    return parser.parse_args(argv)


def _resolve_scenarios(args: argparse.Namespace) -> list[Path]:
    names = list(args.scenarios or [])
    if args.all_scenarios or not names:
        names = list(_DEFAULT_SCENARIOS)
    paths = []
    for name in names:
        path = _SCENARIO_DIR / name
        if not path.is_file():
            raise FileNotFoundError(f"Scenario not found: {path}")
        paths.append(path)
    return paths


def run_all(args: argparse.Namespace) -> RangeScorecard:
    if not args.skip_egress_check:
        assert_range_egress_blocked()

    mode = "live" if args.live_models else "mock"
    pipeline = CortexRangePipeline(mode=mode)
    scorecard = RangeScorecard()

    for path in _resolve_scenarios(args):
        scenario = load_scenario(path)
        scorecard.runs.append(pipeline.run_scenario(scenario))

    if not args.no_duress and (args.all_scenarios or not args.scenarios):
        b_path = _SCENARIO_DIR / "scenario_b_cctv_shield.yaml"
        if b_path.is_file():
            scenario = load_scenario(b_path)
            scorecard.runs.append(pipeline.run_scenario(scenario, approver_override="duress"))

    return scorecard


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.scenarios and not args.all_scenarios:
        args.all_scenarios = True

    scorecard = run_all(args)
    json_path, md_path = write_reports(scorecard, args.reports_dir)

    summary = md_path.read_text(encoding="utf-8")
    print(summary)
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {md_path}")

    if not scorecard.all_checks_passed():
        print("RANGE FAILED: one or more scorecard checks did not meet targets.", file=sys.stderr)
        return 1
    print("RANGE PASSED: all four checks met.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
