"""Predictive Exposure Radar: rank by mission impact, alert on what changes it.

Military/tactical context:
The radar must put the flaw on the path to the financial database above a higher-CVSS
flaw that leads nowhere, stay quiet when intelligence changes for unreachable assets, and
raise every link of a chain when one link becomes likely to be exploited.
"""

from __future__ import annotations

import math
import statistics
from pathlib import Path

import pytest
import yaml

from src.cortex.radar.exposure_radar import (
    ExposureModel,
    ExposureRadar,
    baseline_orders,
    exact_best_set,
    project,
    radar_order,
    simulate,
    synthetic_findings,
)

pytestmark = pytest.mark.cortex
ROOT = Path(__file__).resolve().parents[2]
SCENARIO = yaml.safe_load((ROOT / "range/mock_xiid_mcp/scenarios/enterprise_200.yaml").read_text())
MISSION = yaml.safe_load((ROOT / "range/enterprise/mission_enterprise_200.yaml").read_text())


def _radar():
    return ExposureRadar(SCENARIO["routes"], SCENARIO["vulnerabilities"], MISSION)


def test_epss_projection() -> None:
    assert project({"epss": 0.5}, 30)["epss"] == pytest.approx(0.5)
    assert project({"epss": 0.5}, 60)["epss"] == pytest.approx(0.75)
    assert project({"epss": 0.0}, 90)["epss"] == 0.0


def test_mission_impact_beats_cvss_order() -> None:
    top = _radar().ranked()[0]
    assert (top.finding_id, top.host, top.rank_cvss) == ("SYN-2026-0006", "srv-erp-db-01", 4)
    by_id = {e.finding_id: e for e in _radar().ranked()}
    # The CVSS 9.8 KEV gateway flaw adds nothing: it leads to corporate users, already a modelled foothold.
    assert by_id["SYN-2026-0002"].rank_cvss == 1 and by_id["SYN-2026-0002"].importance == 0


def test_intelligence_on_unreachable_asset_is_quiet() -> None:
    r = _radar()
    assert r.ingest({"type": "kev_added", "finding_id": "SYN-2026-0017"}) == []
    assert r.ingest({"type": "epss_update", "finding_id": "SYN-2026-0017", "epss": 0.97}) == []


def test_rising_epss_raises_the_whole_chain() -> None:
    alerts = _radar().ingest({"type": "epss_update", "finding_id": "SYN-2026-0013", "epss": 0.9})
    assert {a["finding_id"] for a in alerts} == {"SYN-2026-0013", "SYN-2026-0011"}  # CI pipeline -> DC LDAP
    assert all(a["importance_before"] == 0 and a["importance_after"] > 0.05 for a in alerts)


def test_new_finding_activates_existing_link() -> None:
    alerts = _radar().ingest({"type": "new_finding", "finding": {
        "id": "SYN-2026-0099", "host": "srv-backup-01", "component": "srv-backup-01", "service": "smb",
        "cvss": 9.0, "epss": 0.6, "kev": False}})
    assert {a["finding_id"] for a in alerts} == {"SYN-2026-0099", "SYN-2026-0010"}  # file server -> backup


def test_route_change_is_reflected() -> None:
    r = _radar()
    before = r.view["SYN-2026-0006"].importance
    r.ingest({"type": "route_change", "route_id": "rt-users-erpdb", "status": "expired"})
    assert r.view["SYN-2026-0006"].importance < before


def test_greedy_patch_set_matches_exhaustive() -> None:
    model = ExposureModel(SCENARIO["routes"], MISSION)
    gaps = []
    for fs in [SCENARIO["vulnerabilities"]] + [synthetic_findings(SCENARIO["routes"], 18, s) for s in range(4)]:
        order = radar_order(model, fs)
        proj = {f["id"]: project(f, 30) for f in fs}
        for k in (2, 4):
            greedy = model.exposure([p for i, p in proj.items() if i not in order[:k]])[0]
            _, best = exact_best_set(model, fs, k)
            gaps.append(greedy / best - 1)
    assert sum(g < 1e-9 for g in gaps) >= 9 and max(gaps) < 0.10


def test_radar_ordering_reduces_exposure_days() -> None:
    model = ExposureModel(SCENARIO["routes"], MISSION)
    gains = []
    for seed, fs in [(0, SCENARIO["vulnerabilities"])] + [(s, synthetic_findings(SCENARIO["routes"], 18, s))
                                                          for s in range(1, 6)]:
        orders = baseline_orders(fs)
        orders["radar"] = radar_order(model, fs)
        res = simulate(model, fs, orders, samples=120, seed=seed)
        best = min(v.mean_exposure_days for k, v in res.items() if k != "radar")
        assert res["radar"].mean_exposure_days <= best + 1e-9
        gains.append(1 - res["radar"].mean_exposure_days / best)
    assert statistics.median(gains) >= 0.2 and not any(math.isnan(g) for g in gains)
