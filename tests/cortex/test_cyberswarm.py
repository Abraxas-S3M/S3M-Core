"""Sovereign CyberSwarm: minimal signed summaries between isolated regions.

Military/tactical context:
Sovereignty first: nothing identifying leaves a region, everything that arrives is
verified, partitions delay rather than lose, and the measured benefit to a partner region
is reported where it exists and where it does not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from src.cortex.swarm.swarm import Envelope, Region, Summary, SwarmNetwork, cross_region_value, indicator_hmac

pytestmark = pytest.mark.cortex
ROOT = Path(__file__).resolve().parents[2]
POLICY = yaml.safe_load((ROOT / "configs/cortex/swarm_policy.yaml").read_text())
S = yaml.safe_load((ROOT / "range/mock_xiid_mcp/scenarios/enterprise_200.yaml").read_text())
NAMES = [h["id"] for h in S["hosts"]] + sorted({r["target"] for r in S["routes"]})
KEY = b"community-key-for-tests-only-32b"
RAW = "evil-update.example.net"


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 11, 16, 8, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.t


@pytest.fixture
def swarm():
    clock = Clock()
    regions = [Region(r, POLICY, KEY, inventory_names=NAMES, clock=clock)
               for r in ("region-central", "region-west", "region-east")]
    regions[0].local_indicators[RAW] = "srv-ci-01"
    regions[1].local_indicators[RAW] = "srv-web-01"
    return SwarmNetwork(regions), clock


def _draft(region, **kw):
    args = dict(kind="indicator_seen", technique="T1195.002", indicator=RAW, observations=4, severity="high",
                confidence=0.8, classification="restricted", recipients=["region-west"], capability="ghostshift")
    args.update(kw)
    return region.draft(**args)


def test_valid_summary_crosses_and_matches_only_by_keyed_hash(swarm) -> None:
    net, _ = swarm
    c, w = net.regions["region-central"], net.regions["region-west"]
    env = c.release(*_draft(c))
    assert env is not None
    wire = json.dumps(env.summary)
    assert RAW not in wire and "srv-" not in wire and "10." not in wire  # nothing identifying leaves
    net.send(env)
    assert all(d.ok for d in net.deliver()["region-west"])
    m = w.matches()
    assert len(m) == 1 and m[0]["local_match"] == "srv-web-01"  # matched locally, never revealed by central
    outsider = Region("region-east", POLICY, b"other-community-key-000000000000", clock=w.clock)
    outsider.local_indicators[RAW] = "x"
    outsider.inbox = list(w.inbox)
    assert outsider.matches() == []  # without the community key the hash is meaningless


@pytest.mark.parametrize("kw,reason", [
    ({"technique": "beacon to 10.20.2.10"}, "address"),
    ({"technique": "lateral move via srv-erp-db-01"}, "inventory names"),
    ({"technique": f"download {RAW}"}, "raw indicator"),
    ({"observations": 2}, "k-anonymity"),
    ({"recipients": ["region-mars"]}, "not a partner"),
    ({"classification": "secret", "recipients": ["region-west"]}, "not cleared"),
])
def test_release_guard_blocks(swarm, kw, reason) -> None:
    c = swarm[0].regions["region-central"]
    assert c.release(*_draft(c, **kw)) is None
    assert any(reason in r for r in c.blocked[-1][1])


def test_secret_needs_release_officer_and_cleared_partner(swarm) -> None:
    net, _ = swarm
    w = net.regions["region-west"]
    s, n = _draft(w, classification="secret", recipients=["region-central"])
    assert w.guard(s, n, release_officer=True).reasons == ["origin not cleared for secret"]  # west holds no secret
    c = net.regions["region-central"]
    s2, n2 = _draft(c, classification="secret", recipients=["region-west"])
    assert c.guard(s2, n2, release_officer=True).reasons == ["region-west not cleared for secret"]
    s3, n3 = _draft(c, classification="secret", recipients=["region-west"])
    assert "secret needs a release officer" in c.guard(s3, n3).reasons


def test_extra_fields_never_leave(swarm) -> None:
    @dataclass
    class Leaky(Summary):
        raw_log: str = ""

    c = swarm[0].regions["region-central"]
    s, n = _draft(c)
    leaky = Leaky(**s.body(), raw_log="Nov 16 sshd[123]: accepted password for root")
    assert any("fields not allowed" in r for r in c.guard(leaky, n).reasons)


def test_admission_rejects_tamper_replay_expiry_and_misdelivery(swarm) -> None:
    net, clock = swarm
    c, w, e = (net.regions[r] for r in ("region-central", "region-west", "region-east"))
    env = c.release(*_draft(c))
    tampered = Envelope(dict(env.summary, severity="low"), env.signature)
    assert "bad signature" in w.admit(tampered).reasons
    assert w.admit(env).ok and "replay" in w.admit(env).reasons
    assert "not an intended recipient" in e.admit(env).reasons
    late = c.release(*_draft(c, ttl_hours=1))
    clock.t += timedelta(hours=2)
    assert "expired" in w.admit(late).reasons
    forged = Envelope(dict(env.summary, origin="region-mars", summary_id="x-1"), env.signature)
    assert "unknown origin region-mars" in w.admit(forged).reasons


def test_partition_queues_then_delivers_in_order(swarm) -> None:
    net, _ = swarm
    c = net.regions["region-central"]
    net.set_link("region-central", "region-west", False)
    sent = []
    for i in range(3):
        env = c.release(*_draft(c, technique=f"T1059.00{i + 1}"))
        net.send(env)
        sent.append(env.summary["summary_id"])
    assert net.deliver() == {} and net.regions["region-west"].inbox == []
    net.set_link("region-central", "region-west", True)
    net.deliver()
    assert [s["summary_id"] for s in net.regions["region-west"].inbox] == sent


def test_rate_limit(swarm) -> None:
    c = swarm[0].regions["region-central"]
    released = [c.release(*_draft(c, technique=f"T{i:04d}")) for i in range(POLICY["max_per_hour"] + 2)]
    assert sum(r is not None for r in released) == POLICY["max_per_hour"]


def test_partner_benefit_measured_honestly() -> None:
    pytest.importorskip("ortools")
    from src.cortex.cybertwin import build_twin
    from src.cortex.missionguardian.guardian import MissionPolicy
    from src.cortex.wargame.wargame import Campaign, WarGame, flow_tiers_from_policy, paired_ci

    m = yaml.safe_load((ROOT / "range/enterprise/mission_enterprise_200.yaml").read_text())
    pol = MissionPolicy.load(ROOT / "range/enterprise/mission_policy_enterprise_200.yaml")
    tiers = {**{f["id"]: None for f in m["required_flows"]}, **flow_tiers_from_policy(pol)}
    game = WarGame(build_twin(S["routes"], S["vulnerabilities"], m), flow_tiers=tiers)
    insider = cross_region_value(game, game, Campaign("ci", ["srv-ci-01"]), lag_hours=72, runs=120)
    _, lo, hi = paired_ci(insider["losses_with"], insider["losses_without"])
    assert hi < 0 and insider["partner_assets_lost_with"] < 0.6 * insider["partner_assets_lost_without"]
    internet = cross_region_value(game, game, Campaign("inet", ["ext:internet"]), lag_hours=24, runs=120)
    _, lo, hi = paired_ci(internet["losses_with"], internet["losses_without"])
    assert lo < 0 < hi  # fast internet campaigns: no measurable benefit, and the test says so
    assert indicator_hmac(KEY, RAW) == indicator_hmac(KEY, " EVIL-UPDATE.example.net ")
