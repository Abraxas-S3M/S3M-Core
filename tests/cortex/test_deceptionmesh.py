"""DeceptionMesh: decoys where the adversary will meet them, isolated, with bounded telemetry.

Military/tactical context:
Placement is judged by one question: does a decoy fire before a protected asset falls?
The tests check placement quality in-sample and on campaigns the optimiser never saw (where
it does not always win), the effect on containment in the war game, and that deployment
never touches a productive route and never exposes a payload.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

pytest.importorskip("ortools")

from range.run_contract_cycle import contract_range, make_cycle  # noqa: E402
from src.cortex.cybertwin import build_twin  # noqa: E402
from src.cortex.deceptionmesh.mesh import (  # noqa: E402
    build_model,
    candidates,
    collect,
    crown_jewel_adjacent,
    decoy_plan,
    deploy,
    exhaustive,
    greedy,
    placement_value,
    random_baseline,
    retire,
)
from src.cortex.ghostshift.ghostshift import inventory, triggered  # noqa: E402
from src.cortex.missionguardian.guardian import MissionPolicy  # noqa: E402
from src.cortex.wargame.wargame import Campaign, WarGame, flow_tiers_from_policy, paired_ci  # noqa: E402

pytestmark = pytest.mark.cortex
ROOT = Path(__file__).resolve().parents[2]
S = yaml.safe_load((ROOT / "range/mock_xiid_mcp/scenarios/enterprise_200.yaml").read_text())
M = yaml.safe_load((ROOT / "range/enterprise/mission_enterprise_200.yaml").read_text())
TWIN = build_twin(S["routes"], S["vulnerabilities"], M)
CAMPAIGNS = [["grp:corp-users"], ["ext:internet"], ["srv-ci-01"]]
WORKDAY = datetime(2026, 11, 16, 10, 0, tzinfo=ZoneInfo("Asia/Riyadh"))


@pytest.fixture(scope="module")
def model():
    return build_model(TWIN, CAMPAIGNS, candidates(TWIN), runs=150)


def test_candidates_exclude_internet_and_protected_assets() -> None:
    c = candidates(TWIN)
    assert not any(x.startswith("ext:") for x in c) and not set(c) & TWIN.protected


def test_greedy_matches_exhaustive(model) -> None:
    cands = candidates(TWIN)
    for k in (1, 2, 3):
        g = greedy(model, cands, k)
        assert model.score(g) == pytest.approx(exhaustive(model, cands, k)[1])


def test_placement_beats_common_practice_in_sample(model) -> None:
    cands = candidates(TWIN)
    g = greedy(model, cands, 3)
    assert model.score(g) >= 0.85
    assert model.score(crown_jewel_adjacent(TWIN, cands, 3)) <= 0.65
    assert random_baseline(model, cands, 3) <= 0.45
    assert model.lead_hours(g) > 12  # alarms arrive many hours before the first loss


def test_placement_on_unseen_campaigns_is_reported_honestly() -> None:
    """Train on every other entry point, test on the held-out campaign. Better than random on all
    three; better than or equal to crown-jewel placement on two of three, worse on one."""
    allc = candidates(TWIN)
    entries = [[c] for c in allc] + [["ext:internet"]]
    wins, ties_or_wins = 0, 0
    for held in CAMPAIGNS:
        cands = [c for c in allc if c not in held]
        g = greedy(build_model(TWIN, [e for e in entries if e != held], cands, runs=40, seed=2), cands, 3)
        test = build_model(TWIN, [held], cands, runs=150, seed=9)
        assert test.score(g) > random_baseline(test, cands, 3)
        cj = test.score(crown_jewel_adjacent(TWIN, cands, 3))
        wins += test.score(g) > cj
        ties_or_wins += test.score(g) >= cj
    assert wins == 2 and ties_or_wins == 2


def test_decoys_reduce_losses_in_the_war_game(model) -> None:
    pol = MissionPolicy.load(ROOT / "range/enterprise/mission_policy_enterprise_200.yaml")
    tiers = {**{f["id"]: None for f in M["required_flows"]}, **flow_tiers_from_policy(pol)}
    v = placement_value(TWIN, WarGame(TWIN, flow_tiers=tiers), greedy(model, candidates(TWIN), 3),
                        campaign=Campaign("phish", ["grp:corp-users"]), runs=120)
    _, lo, hi = paired_ci(v["losses_with"], v["losses_without"])
    assert hi < 0 and v["assets_lost_with"] < 0.5 * v["assets_lost_without"]


def test_range_deploy_isolated_bounded_and_reversible(tmp_path, model) -> None:
    plan = decoy_plan(greedy(model, candidates(TWIN), 3))
    plan.append({"decoy_id": "decoy-9-internet", "attach": "ext:internet", "service": "https", "persona": "portal"})
    attach = {d["decoy_id"]: d["attach"] for d in plan}
    with contract_range() as rng:
        original = rng.state.model.list_routes()
        cycle, cortex = make_cycle(rng, workdir=tmp_path, case_id="deception", sandbox="sbx-range-full",
                                   clock=lambda: WORKDAY)

        async def go():
            try:
                rep = await deploy(plan, cycle=cycle, case_id="deception")
                for d in plan[:2]:
                    rng.admin({"mode": "attacker_touch", "decoy_id": d["decoy_id"], "source": d["attach"], "depth": 2})
                rng.admin({"mode": "attacker_touch", "decoy_id": plan[0]["decoy_id"], "source": plan[0]["attach"],
                           "depth": 3})
                ev = await collect(cycle, decoy_attach=attach)
                gone = await retire(rep.deployed, cycle=cycle, case_id="deception")
                return rep, ev, gone
            finally:
                await cortex.close()

        rep, ev, gone = asyncio.run(go())
        after_retire = rng.state.model.list_routes()
    assert rep.deployed == [d["decoy_id"] for d in plan[:3]]
    assert rep.refused[0]["decoy"] == "decoy-9-internet" and "CONFLICT" in rep.refused[0]["reason"]
    assert rep.productive_routes_unchanged and rep.decoys_isolated and len(rep.lure_routes) == 3
    first = next(i for i in ev["interactions"] if i["decoy_id"] == plan[0]["decoy_id"])
    assert set(first) == {"decoy_id", "source", "first_seen", "last_seen", "count", "max_depth"}  # no payload
    assert first["count"] == 2 and first["max_depth"] == 3
    assert ev["evidence"]["hosts"] == sorted({plan[0]["attach"], plan[1]["attach"]})
    secrets = inventory(S["routes"], S["stlinks"], S["vulnerabilities"], M)
    expected = {x.secret_id for x in secrets if x.host in ev["evidence"]["hosts"]}
    assert {x.secret_id for x in triggered(secrets, ev["evidence"])} == expected  # evidence feeds GhostShift
    assert gone == rep.deployed and after_retire == original  # fully reversible
