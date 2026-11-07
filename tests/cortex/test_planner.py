#!/usr/bin/env python3
"""Tests for CortexPlanner change-planning service."""

import json
import os
import random
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from s3m_core.memory.knowledge_graph import S3MKnowledgeGraph
from src.cortex.fixtures import cctv_reachability_graph
from src.cortex.planner import CortexPlanner
from src.cortex.reachability import plan_mrc, plan_mrc_reference, random_small_graph, synthetic_graph


@pytest.fixture
def planner(tmp_path):
    cfg = Path("configs/cortex.yaml").read_text(encoding="utf-8")
    custom = tmp_path / "cortex.yaml"
    custom.write_text(cfg.replace("data/cortex/cases", str(tmp_path / "cases")), encoding="utf-8")
    return CortexPlanner(config_path=str(custom))


def test_cctv_planner_reproduces_risk_drop(planner):
    graph = cctv_reachability_graph()
    change = planner.propose(
        graph,
        target_risk=0.03,
        budget=1.0,
        case_id="cctv-case-001",
    )
    assert change.initial_risk == pytest.approx(0.307, abs=0.01)
    assert change.projected_final_risk == pytest.approx(0.022, abs=0.01)
    assert graph.required_flows_reachable()
    after = graph.clone()
    hf = float(planner._mrc.get("harden_factor", 0.08))
    for step in change.steps:
        if step.action == "harden":
            after.apply_harden(step.edge_id, hf)
        else:
            after.apply_remove(step.edge_id)
    assert after.required_flows_reachable()


def test_shield_queue_kev_above_low_epss(planner):
    graph = cctv_reachability_graph()
    vulns = [
        {
            "id": "v-low",
            "epss": 0.85,
            "kev": False,
            "criticality": 0.4,
            "days_to_patch": 20,
            "asset_id": "cam_vlan",
        },
        {
            "id": "v-kev",
            "epss": 0.15,
            "kev": True,
            "criticality": 0.7,
            "days_to_patch": 5,
            "asset_id": "nvr",
        },
    ]
    ranked = planner.shield_queue(vulns, graph)
    assert len(ranked) >= 2
    assert ranked[0]["id"] == "v-kev"
    assert ranked[0]["shield_score"] > ranked[1]["shield_score"]


def test_optimised_mrc_matches_reference_on_random_graphs():
    rng = random.Random(2025)
    for _ in range(20):
        graph = random_small_graph(rng, n_nodes=8 + rng.randint(0, 6))
        ref = plan_mrc_reference(graph, budget=3.0)
        opt = plan_mrc(graph, budget=3.0)
        assert [(a.edge_id, a.action) for a in ref.actions] == [(a.edge_id, a.action) for a in opt.actions]


@pytest.mark.slow
def test_five_thousand_node_plan_under_thirty_seconds():
    graph = synthetic_graph(5000, seed=7)
    t0 = time.perf_counter()
    plan_mrc(graph, budget=5.0)
    elapsed = time.perf_counter() - t0
    assert elapsed < 30.0, f"planning took {elapsed:.2f}s"


def test_change_request_json_roundtrip_and_case_storage(planner, tmp_path):
    graph = cctv_reachability_graph()
    case_id = "case-json-42"
    change = planner.propose(graph, target_risk=0.05, budget=1.0, case_id=case_id)
    raw = json.loads(change.to_json())
    assert raw["case_id"] == case_id
    path = planner.store_change_request(case_id, change)
    assert path.is_file()
    loaded = planner.load_change_request(case_id)
    assert loaded.to_dict() == change.to_dict()


def test_build_graph_from_knowledge_graph(planner):
    with tempfile.TemporaryDirectory() as tmp:
        kg = S3MKnowledgeGraph(storage_path=str(Path(tmp) / "kg.json"))
        kg.add_entity("internet", "system", {"cortex_kind": "connector", "foothold": True})
        kg.add_entity("nvr", "service", {"cortex_kind": "host", "criticality": 0.8})
        kg.add_entity("crown", "service", {"cortex_kind": "datastore", "criticality": 1.0})
        kg.add_relationship("internet", "nvr", "depends_on", {"edge_kind": "management"})
        kg.add_relationship("nvr", "crown", "depends_on", {"edge_kind": "can_access"})
        graph = planner.build_graph(
            kg,
            xiid_inventory={},
            required_flows=[("internet", "nvr")],
            protected=["crown"],
        )
        assert "internet" in graph.nodes
        assert graph.system_risk() > 0.0
