"""CyberTwin calibration: evidence-learned edge beliefs, decay, intervals, robust planning.

Military/tactical context:
Risk numbers shown to a commander must say how sure they are. These tests validate the
calibration against a hidden synthetic ground truth - interval coverage, error reduction,
learned trust in the heuristic, decay of stale evidence - and pin that pressure telemetry
never masquerades as exploit success.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
import yaml

from range.run_contract_cycle import contract_range, run_contract_cycle
from src.cortex.calibration import CalibrationStore, Outcome, simulate_exercises, synthetic_truth
from src.cortex.cybertwin import build_twin
from src.cortex.mcp_contract.telemetry import generate

pytestmark = pytest.mark.cortex
ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def scenario():
    return yaml.safe_load((ROOT / "range/mock_xiid_mcp/scenarios/enterprise_200.yaml").read_text())


@pytest.fixture(scope="module")
def twin(scenario):
    m = yaml.safe_load((ROOT / "range/enterprise/mission_enterprise_200.yaml").read_text())
    return build_twin(scenario["routes"], scenario["vulnerabilities"], m)


def test_coverage_and_error_against_hidden_truth(twin) -> None:
    covered, err_h, err_p = [], [], []
    for seed in range(10):
        truth = synthetic_truth(twin, seed=seed)
        st = CalibrationStore(twin)
        outs = simulate_exercises(truth, seed=100 + seed, when=NOW)
        st.add_outcomes(outs)
        tested = {o.route_id for o in outs}
        rng = np.random.default_rng(seed)
        for rid, b in st.beliefs(NOW).items():
            lo, hi = b.interval(rng)
            covered.append(lo <= truth[rid] <= hi)
            if rid in tested:
                err_h.append(abs(twin.edges[twin.route_edge[rid]].p - truth[rid]))
                err_p.append(abs(b.mean - truth[rid]))
    assert np.mean(covered) >= 0.78  # nominal 0.90; measured ~0.84 under a misspecified truth model
    assert np.mean(err_p) < 0.6 * np.mean(err_h)


def test_trust_in_heuristic_is_learned(twin) -> None:
    ks = {}
    for spread in (0.2, 1.2):
        st = CalibrationStore(twin)
        st.add_outcomes(simulate_exercises(synthetic_truth(twin, seed=3, spread=spread), seed=9, coverage=0.9, when=NOW))
        st.beliefs(NOW)
        ks[spread] = st.last_prior_strength
    assert ks[0.2] > 2 * ks[1.2]


def test_stale_evidence_decays_toward_prior(twin) -> None:
    st = CalibrationStore(twin)
    st.add_outcomes([Outcome("rt-users-erpdb", 40, 2, NOW, "red_team")])
    fresh, stale = st.beliefs(NOW)["rt-users-erpdb"], st.beliefs(NOW + timedelta(days=365))["rt-users-erpdb"]
    rng = np.random.default_rng(0)
    assert stale.effective_attempts < 0.1 * fresh.effective_attempts
    assert np.diff(stale.interval(rng))[0] > np.diff(fresh.interval(rng))[0]
    assert abs(stale.mean - stale.prior_mean) < abs(fresh.mean - fresh.prior_mean)


def test_pressure_is_separate_from_success(twin, scenario) -> None:
    st = CalibrationStore(twin)
    before = {r: b.mean for r, b in st.beliefs(NOW).items()}
    st.add_telemetry(generate(scenario, start=NOW - timedelta(hours=1), hours=1))
    after = st.beliefs(NOW)
    assert max(after.values(), key=lambda b: b.pressure_per_hour).route_id == "rt-cams-corp"
    assert {r: b.mean for r, b in after.items()} == before


def test_rejects_bad_evidence(twin) -> None:
    st = CalibrationStore(twin)
    with pytest.raises(KeyError):
        st.add_outcomes([Outcome("rt-nope", 5, 1, NOW, "exercise")])
    with pytest.raises(ValueError):
        st.add_outcomes([Outcome("rt-users-erpdb", 5, 7, NOW, "exercise")])


def test_intervals_are_ordered_and_quantile_is_conservative(twin) -> None:
    st = CalibrationStore(twin)
    st.add_outcomes(simulate_exercises(synthetic_truth(twin, seed=4), seed=44, when=NOW))
    iv = st.exposure_intervals(NOW, samples=150)
    assert all(v["p05"] <= v["p50"] <= v["p95"] for v in iv.values())
    mean_tw, q90_tw = st.calibrated_twin(NOW), st.calibrated_twin(NOW, quantile=0.9)
    for a in twin.protected:
        assert max(q90_tw.max_path_prob(f, a) for f in twin.footholds) >= \
            max(mean_tw.max_path_prob(f, a) for f in twin.footholds) - 1e-9


def test_cycle_with_calibration_verifies(twin, tmp_path) -> None:
    st = CalibrationStore(twin)
    st.add_outcomes(simulate_exercises(synthetic_truth(twin, seed=5), seed=55, when=NOW))
    with contract_range() as rng:
        report, _ = asyncio.run(run_contract_cycle(rng, workdir=tmp_path, case_id="t-cal", calibration=st))
        assert report.outcome == "verified" and report.verification["matches_prediction"]
        cal = report.analysis["calibration"]
        assert cal["planning_quantile"] == 0.9 and set(cal["exposure_intervals"]) == set(twin.protected)
