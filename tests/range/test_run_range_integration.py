"""Integration test for run_range scorecard (egress check mocked)."""

from __future__ import annotations

from unittest.mock import patch

from range.run_range import parse_args, run_all
from range.scoring import RangeScorecard


def test_run_all_scenarios_pass_four_checks(tmp_path) -> None:
    args = parse_args(["--all-scenarios", "--reports-dir", str(tmp_path / "reports"), "--skip-egress-check"])
    with patch("range.run_range.assert_range_egress_blocked"):
        scorecard = run_all(args)
    assert isinstance(scorecard, RangeScorecard)
    assert len(scorecard.runs) >= 4
    assert scorecard.all_checks_passed() is True
