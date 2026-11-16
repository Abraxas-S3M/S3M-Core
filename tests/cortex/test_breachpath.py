"""BreachPath exact optimiser: optimality, constraints, explanations, baseline comparison.

Military/tactical context:
A plan the commander is told is "the cheapest safe option" must be provably so. These
tests check the solver against exhaustive search on small networks, prove it never does
worse than the greedy planner it replaces, and pin the mission constraints it must obey.
"""

from __future__ import annotations

import itertools
from pathlib import Path

import pytest
import yaml

pytest.importorskip("ortools")

from src.cortex.breachpath.analysis import compare_with_greedy, frontier, scale_twin  # noqa: E402
from src.cortex.breachpath.optimizer import (  # noqa: E402
    PlanConstraints,
    PlannedAction,
    _allowed,
    apply_actions,
    exposure,
    optimize,
    plan_objective,
)
from src.cortex.cybertwin import build_twin  # noqa: E402

pytestmark = pytest.mark.cortex
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def twin():
    s = yaml.safe_load((ROOT / "range/mock_xiid_mcp/scenarios/enterprise_200.yaml").read_text())
    m = yaml.safe_load((ROOT / "range/enterprise/mission_enterprise_200.yaml").read_text())
    return build_twin(s["routes"], s["vulnerabilities"], m)


def _relevant_edges(tw):
    """Edges between a foothold-reachable node and a node that reaches a protected asset.

    Any action elsewhere cannot change exposure, so it can never be in a cheapest plan;
    excluding it keeps exhaustive search exact while shrinking it.
    """
    import networkx as nx

    g = nx.DiGraph()
    for e in tw.edges.values():
        if not e.removed and e.effective_p > 0:
            g.add_edge(e.source, e.target)
    fwd = set().union(*[nx.descendants(g, f) | {f} for f in tw.footholds if f in g])
    back = set().union(*[nx.ancestors(g, a) | {a} for a in tw.protected if a in g])
    return {eid for eid, e in tw.edges.items() if e.source in fwd and e.target in back}


def _brute_force(tw, thresholds, c):
    allowed = {e: a for e, a in _allowed(tw, c).items() if e in _relevant_edges(tw)}
    options = []
    for eid, acts in allowed.items():
        rid = tw.route_meta[eid].route_id
        sessions = tw.route_meta[eid].observed_sessions_30d
        options.append([None] + [
            PlannedAction(rid, a, 1.0 if a == "narrow" else 1.25, 0 if a == "narrow" else sessions,
                          True if a == "narrow" else c.expire_reversible)
            for a in sorted(acts)
        ])
    best = None
    for combo in itertools.product(*options):
        acts = [a for a in combo if a is not None]
        exp = exposure(apply_actions(tw, acts))
        if all(exp[k] <= thresholds[k] + 1e-9 for k in exp):
            obj = plan_objective(acts)
            best = obj if best is None else min(best, obj)
    return best


@pytest.mark.parametrize("seed", range(1, 13))
def test_matches_exhaustive_search_on_small_networks(seed) -> None:
    tw = scale_twin(24, seed=seed, n_protected=2)
    c = PlanConstraints(expire_policy="any")
    if len([e for e in _allowed(tw, c) if e in _relevant_edges(tw)]) > 12:
        pytest.skip("search space too large for exhaustive check")
    th = {a: v * 0.3 for a, v in exposure(tw).items()}
    plan = optimize(tw, threshold=1.0, asset_thresholds=th, constraints=c)
    brute = _brute_force(tw, th, c)
    if brute is None:
        assert plan.residual, "exhaustive search found no feasible plan, solver must report residual"
    else:
        assert plan.status in {"OPTIMAL", "NO_ACTION_NEEDED"}
        assert plan.meets_thresholds
        assert plan_objective(plan.actions) == brute


@pytest.mark.parametrize("n,seed", [(100, 1), (300, 2), (1000, 3)])
def test_never_worse_than_greedy(n, seed) -> None:
    tw = scale_twin(n, seed=seed)
    c = PlanConstraints(expire_policy="any")
    th = {a: v * 0.25 for a, v in exposure(tw).items()}
    plan = optimize(tw, threshold=1.0, asset_thresholds=th, constraints=c)
    cmp = compare_with_greedy(tw, plan, c)
    if cmp["greedy_reached"]:
        assert cmp["exact_objective"] <= cmp["greedy_objective"]


def test_enterprise_plan_and_residual_explanation(twin) -> None:
    plan = optimize(twin, threshold=0.30)
    assert plan.status == "OPTIMAL"
    assert {(a.action, a.route_id) for a in plan.actions} == {("expire", "rt-users-erpdb"), ("narrow", "rt-users-jump-rdp")}
    assert plan.disrupted_sessions_30d == 0
    # The domain controller cannot go below ~0.317 with route policy: required Kerberos flow.
    res = {(r.foothold, r.asset): r for r in plan.residual}
    dc = res[("grp:corp-users", "srv-dc-01")]
    assert any("required:rt-users-dc" in b for b in dc.blocking)
    assert twin.broken_flows() == [] and apply_actions(twin, plan.actions).broken_flows() == []


def test_mission_constraints_are_hard(twin) -> None:
    base = optimize(twin, threshold=0.10)
    assert any(a.route_id == "rt-users-erpdb" for a in base.actions)
    forbid = optimize(twin, threshold=0.10, constraints=PlanConstraints(forbidden={"rt-users-erpdb": {"expire", "narrow"}}))
    assert all(a.route_id != "rt-users-erpdb" for a in forbid.actions)
    capped = optimize(twin, threshold=0.10, constraints=PlanConstraints(max_changes=1))
    assert len(capped.actions) <= 1
    none = optimize(twin, threshold=0.10, constraints=PlanConstraints(expire_policy="none"))
    assert all(a.action == "narrow" for a in none.actions)
    busy = optimize(twin, threshold=0.10, constraints=PlanConstraints(expire_policy="any", max_disrupted_sessions=0))
    assert busy.disrupted_sessions_30d == 0


def test_frontier_is_monotone(twin) -> None:
    rows = frontier(twin)
    costs = [r["cost"] for r in rows]
    assert costs == sorted(costs)  # stricter thresholds never cost less
    assert rows[0]["status"] == "NO_ACTION_NEEDED"


def test_beats_greedy_on_enterprise(twin) -> None:
    plan = optimize(twin, threshold=0.30)
    cmp = compare_with_greedy(twin, plan)
    assert cmp["greedy_reached"] and cmp["exact_objective"] < cmp["greedy_objective"]


def test_defense_cycle_executes_exact_plan(tmp_path) -> None:
    import asyncio

    from range.run_contract_cycle import contract_range, run_contract_cycle

    with contract_range() as rng:
        report, _ = asyncio.run(run_contract_cycle(rng, workdir=tmp_path, case_id="t-bp", exposure_target=0.30))
        assert report.recommended_option == "OPT-D"
        assert report.outcome == "verified" and report.verification["matches_prediction"]
        assert {c["route_id"] for c in report.changes} == {"rt-users-erpdb", "rt-users-jump-rdp"}
        assert rng.state.writes_applied == 2
        opt_d = next(o for o in report.options if o["option_id"] == "OPT-D")
        assert opt_d["proven_optimal"] and opt_d["residual_exposure"]
