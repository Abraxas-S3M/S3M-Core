"""Intent2Fabric: controlled-English intents compiled into proved, monotone route changes.

Military/tactical context:
An operator's sentence must become exactly the changes it implies - no more (never widen
access, never break a mission flow) and no less (every intent holds afterwards). These
tests pin the parser, the compiler, the proof and execution through the defense cycle.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

import pytest
import yaml

from range.run_contract_cycle import contract_range, run_contract_cycle
from src.cortex.cybertwin import build_twin
from src.cortex.intent2fabric.intents import IntentError, compile_intents, load_intents

pytestmark = pytest.mark.cortex
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def twin():
    s = yaml.safe_load((ROOT / "range/mock_xiid_mcp/scenarios/enterprise_200.yaml").read_text())
    m = yaml.safe_load((ROOT / "range/enterprise/mission_enterprise_200.yaml").read_text())
    return build_twin(s["routes"], s["vulnerabilities"], m)


@pytest.fixture(scope="module")
def entries():
    return yaml.safe_load((ROOT / "range/enterprise/intents_enterprise_200.yaml").read_text())["intents"]


def test_parser_round_trips_and_rejects(twin, entries) -> None:
    intents = load_intents(entries, twin)
    assert [i.kind for i in intents] == ["only_reach", "only_from", "deny_services", "restrict_prefix", "only_reach"]
    again = load_intents([{"id": i.intent_id, "say": i.canonical()} for i in intents], twin)
    assert again == intents  # canonical sentence parses back to the same intent
    for bad in ["cameras may only reach the recorder",  # unknown names
                "grp:cctv-cams may only reach srv-nvr-99",  # unknown target
                "no gopher from ext:internet",  # unknown service
                "grp:corp-users may reach srv-file-01 over smb only from 10.10.4.1/22",  # host bits set
                "please lock everything down"]:
        with pytest.raises(IntentError):
            load_intents([{"id": "X", "say": bad}], twin)


def test_compile_and_proof(twin, entries) -> None:
    c = compile_intents(twin, load_intents(entries, twin))
    got = {(ch.xiid_action, ch.route_id) for ch in c.changes}
    assert got == {("expire_route", "rt-cams-corp"), ("expire_route", "rt-users-erpdb"),
                   ("expire_route", "rt-inet-jump-ssh"), ("narrow_route", "rt-users-file"),
                   ("expire_route", "rt-mail-file")}
    p = c.proof
    assert p["all_satisfied_or_conflicted"] and p["monotone_tightening"] and p["required_flows_intact"]
    assert not c.conflicts and p["routes_after"] == p["routes_before"] - 4


def test_conflicts_with_required_flows_are_reported_not_resolved(twin) -> None:
    c = compile_intents(twin, load_intents(
        [{"id": "I-USERS", "say": "grp:corp-users may only reach srv-erp-app-01 and srv-hr-app-01"}], twin))
    conflicted = {x.route_id for x in c.conflicts}
    assert {"rt-users-dc", "rt-users-file", "rt-users-siem"} <= conflicted
    assert not conflicted & {ch.route_id for ch in c.changes}
    assert c.proof["required_flows_intact"] and not c.proof["intents"]["I-USERS"]["unexplained_violations"]


def test_random_intents_never_widen_access(twin) -> None:
    rng = random.Random(7)
    nodes = sorted(twin.nodes)
    services = sorted({m.service for m in twin.route_meta.values()})
    for _ in range(60):
        kind = rng.choice(["only", "from", "deny"])
        a, b = rng.sample(nodes, 2)
        say = {"only": f"{a} may only reach {b}", "from": f"only {a} may reach {b}",
               "deny": f"no {rng.choice(services)} from {a}"}[kind]
        c = compile_intents(twin, load_intents([{"id": "R", "say": say}], twin))
        assert c.proof["monotone_tightening"] and c.proof["required_flows_intact"], say


def test_cycle_executes_intents_through_contract(twin, entries, tmp_path) -> None:
    with contract_range() as rng:
        report, _ = asyncio.run(run_contract_cycle(rng, workdir=tmp_path, case_id="t-i2f",
                                                   intents=load_intents(entries, twin)))
        assert report.recommended_option == "OPT-I" and report.outcome == "verified"
        assert rng.state.writes_applied == 5
        routes = {r["id"]: r for r in rng.state.model.list_routes()}
        assert routes["rt-users-file"]["narrow_to"] == "10.10.4.0/22"
        assert routes["rt-cams-corp"]["status"] == "expired"
        assert report.analysis["intents"]["proof"]["monotone_tightening"]
