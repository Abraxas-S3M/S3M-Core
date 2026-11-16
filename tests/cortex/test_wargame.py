"""CyberWarGame: compare containment playbooks under identical attacker luck.

Military/tactical context:
A war game is only useful if its comparisons are fair (common random numbers), its
claims are statistically honest (paired intervals), and it respects what must keep
running (tier-weighted availability loss). These tests check those properties and the
findings they produce on the enterprise_200 twin.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytest.importorskip("ortools")

from src.cortex.cybertwin import build_twin  # noqa: E402
from src.cortex.missionguardian.guardian import MissionPolicy  # noqa: E402
from src.cortex.wargame.wargame import (  # noqa: E402
    Campaign,
    PlaybookResult,
    WarGame,
    flow_tiers_from_policy,
    paired_ci,
    pareto,
    recommend,
)

pytestmark = pytest.mark.cortex
ROOT = Path(__file__).resolve().parents[2]
S = yaml.safe_load((ROOT / "range/mock_xiid_mcp/scenarios/enterprise_200.yaml").read_text())
M = yaml.safe_load((ROOT / "range/enterprise/mission_enterprise_200.yaml").read_text())
POLICY = MissionPolicy.load(ROOT / "range/enterprise/mission_policy_enterprise_200.yaml")
TIERS = {**{f["id"]: None for f in M["required_flows"]}, **flow_tiers_from_policy(POLICY)}


def _game(**detection) -> WarGame:
    return WarGame(build_twin(S["routes"], S["vulnerabilities"], M), flow_tiers=TIERS, detection=detection or None)


@pytest.fixture(scope="module")
def insider():
    return _game().compare(Campaign("ci-insider", ["srv-ci-01"]), runs=150, seed=1)


@pytest.fixture(scope="module")
def vpn():
    return _game().compare(Campaign("vpn", ["ext:internet"]), runs=150, seed=1)


def test_common_random_numbers_make_runs_reproducible() -> None:
    g = _game()
    a = g.compare(Campaign("x", ["srv-ci-01"], hours=48), runs=30, seed=5)
    b = g.compare(Campaign("x", ["srv-ci-01"], hours=48), runs=30, seed=5)
    assert all(a[k].losses == b[k].losses and a[k].flow_losses == b[k].flow_losses for k in a)


def test_every_playbook_beats_doing_nothing(insider, vpn) -> None:
    for res in (insider, vpn):
        for name, r in res.items():
            if name == "none":
                continue
            _, lo, hi = paired_ci(r.losses, res["none"].losses)
            assert hi < 0, name  # fewer protected assets lost, interval excludes zero


def test_optimised_cut_costs_no_availability(insider, vpn) -> None:
    for res in (insider, vpn):
        assert res["breachpath_adaptive"].mean_flow_hours_lost == 0
        assert res["quarantine_detected"].mean_flow_hours_lost > 400
        assert "breachpath_adaptive" in pareto(res)
        assert recommend(res, max_flow_hours=200) == "breachpath_adaptive"


def test_unconstrained_recommendation_trades_availability(insider) -> None:
    rec = recommend(insider, max_flow_hours=1e9)
    assert rec in {"ring_fence_assets", "quarantine_detected"}
    assert insider[rec].mean_assets_lost < insider["breachpath_adaptive"].mean_assets_lost


def test_no_overclaiming_when_difference_is_noise(vpn) -> None:
    """Optimised cut vs quarantine in the VPN campaign: the interval straddles zero."""
    _, lo, hi = paired_ci(vpn["breachpath_adaptive"].losses, vpn["quarantine_detected"].losses)
    assert lo < 0 < hi


def test_detection_is_the_bottleneck_for_phishing() -> None:
    camp = Campaign("phish", ["grp:corp-users"])
    slow = _game().compare(camp, runs=120, seed=1)
    fast = _game(grp=0.05).compare(camp, runs=120, seed=1)
    assert slow["quarantine_detected"].mean_assets_lost > 3.5
    assert fast["quarantine_detected"].mean_assets_lost < slow["quarantine_detected"].mean_assets_lost - 0.7
    # Route cuts alone barely help: the dominant path uses the protected Kerberos route and identity edges.
    assert slow["none"].mean_assets_lost - fast["breachpath_adaptive"].mean_assets_lost < 0.3


def test_pareto_drops_dominated() -> None:
    r = {k: PlaybookResult(k, 0, a, f, 0, 0) for k, a, f in [("a", 1, 10), ("b", 2, 5), ("c", 2, 10)]}
    assert pareto(r) == ["a", "b"]
