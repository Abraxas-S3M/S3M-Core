"""Cortex change-planning service: vulnerability/incident → reversible change request."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import yaml

from s3m_core.memory.knowledge_graph import S3MKnowledgeGraph
from src.autonomy.decision_engine.multi_objective import ParetoOptimizer
from src.cortex.pccp import ChangeRequest, build_change
from src.cortex.reachability import (
    GraphTooLargeError,
    ReachabilityGraph,
    plan_mrc,
    shield_priority,
)

_CORTEX_ENTITY_TYPES = {
    "process",
    "host",
    "identity",
    "ai_agent",
    "datastore",
    "stlink",
    "connector",
}

_KG_TYPE_MAP = {
    "system": "host",
    "service": "process",
    "tool": "connector",
    "person": "identity",
    "organization": "identity",
    "vulnerability": "process",
    "codebase": "datastore",
    "document": "datastore",
    "concept": "connector",
}

_REL_TO_EDGE_KIND = {
    "uses": "authenticates_as",
    "depends_on": "depends_on",
    "related_to": "connects_to",
    "part_of": "part_of",
    "discovered_by": "management",
    "solved_with": "management",
    "caused_by": "lateral_movement",
}


class CortexPlanner:
    """Builds reachability models, ranks vulns, and proposes MRC-backed changes."""

    def __init__(self, config_path: str = "configs/cortex.yaml") -> None:
        path = Path(config_path)
        if not path.is_file():
            raise FileNotFoundError(f"Cortex config not found: {config_path}")
        self._config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        self._mrc = self._config.get("mrc", {})
        self._shield = self._config.get("vulnerability_shield", {})
        self._planner = self._config.get("planner", {})
        self._tie_resolver = ParetoOptimizer(
            weights={
                "survival": 0.5,
                "mission_progress": 0.2,
                "roe_risk": 0.25,
                "fuel_cost": 0.05,
                "info_gain": 0.0,
            }
        )

    @property
    def case_storage_dir(self) -> Path:
        return Path(str(self._planner.get("case_storage_dir", "data/cortex/cases")))

    def build_graph(
        self,
        kg: S3MKnowledgeGraph,
        xiid_inventory: Mapping[str, Any],
        required_flows: Sequence[Tuple[str, str]],
        protected: Sequence[str],
    ) -> ReachabilityGraph:
        max_nodes = int(self._mrc.get("max_graph_nodes", 10_000))
        edge_defaults: Dict[str, float] = dict(self._mrc.get("edge_defaults", {}))
        default_p = float(edge_defaults.get("default", 0.5))

        g = ReachabilityGraph(max_graph_nodes=max_nodes)
        inventory = dict(xiid_inventory or {})

        for node_id, data in kg.graph.nodes(data=True):
            attrs = dict(data.get("attributes", {}))
            kind = str(attrs.get("cortex_kind") or attrs.get("xiid_kind") or "").strip().lower()
            if not kind:
                et = str(data.get("entity_type", "system")).lower()
                kind = _KG_TYPE_MAP.get(et, "host")
            if kind not in _CORTEX_ENTITY_TYPES:
                kind = "host"
            crit = float(attrs.get("criticality", inventory.get(node_id, {}).get("criticality", 0.5)))
            extra_attrs = {k: v for k, v in attrs.items() if k != "criticality"}
            g.add_node(str(node_id), kind, criticality=crit, **extra_attrs)

        for inv_id, inv_meta in inventory.items():
            if inv_id in g.nodes:
                continue
            kind = str(inv_meta.get("kind", "host")).lower()
            if kind not in _CORTEX_ENTITY_TYPES:
                kind = "host"
            g.add_node(
                str(inv_id),
                kind,
                criticality=float(inv_meta.get("criticality", 0.5)),
                **{k: v for k, v in inv_meta.items() if k not in {"kind", "criticality"}},
            )

        footholds: List[str] = []
        for node_id, data in kg.graph.nodes(data=True):
            attrs = data.get("attributes", {})
            if attrs.get("foothold") or attrs.get("is_foothold"):
                footholds.append(str(node_id))
        if not footholds:
            for inv_id, inv_meta in inventory.items():
                if inv_meta.get("foothold"):
                    footholds.append(str(inv_id))

        for source, target, edge_data in kg.graph.edges(data=True):
            if source not in g.nodes or target not in g.nodes:
                continue
            rel = str(edge_data.get("relationship_type", "related_to")).lower()
            kind = str(edge_data.get("metadata", {}).get("edge_kind", _REL_TO_EDGE_KIND.get(rel, rel)))
            p = edge_data.get("metadata", {}).get("traversal_p")
            if p is None:
                p = edge_defaults.get(kind, edge_defaults.get(rel, default_p))
            cost = float(edge_data.get("metadata", {}).get("action_cost", self._mrc.get("default_action_cost", 1.0)))
            disruption = float(edge_data.get("metadata", {}).get("disruption", 0.3))
            g.add_edge(str(source), str(target), kind, float(p), cost=cost, disruption=disruption)

        prot = [str(p) for p in protected]
        flows = [(str(a), str(b)) for a, b in required_flows]
        if not footholds and g.nodes:
            footholds = [next(iter(g.nodes))]
        g.set_scope(footholds, prot, flows)
        return g

    def shield_queue(self, vulns: Sequence[Dict[str, Any]], graph: ReachabilityGraph) -> List[Dict[str, Any]]:
        threshold = float(self._shield.get("shield_threshold", 0.35))
        weights = dict(self._shield.get("weights", {}))
        ranked: List[Dict[str, Any]] = []

        for vuln in vulns:
            asset = str(vuln.get("asset_id") or vuln.get("host") or "")
            reach = 0.0
            if asset and asset in graph.nodes:
                reach = max(graph.max_path_prob(f, asset) for f in graph.footholds) if graph.footholds else 0.0
            score = shield_priority(vuln, reachability_score=reach, weights=weights)
            entry = dict(vuln)
            entry["shield_score"] = score
            entry["reachability_score"] = reach
            if score >= threshold:
                ranked.append(entry)

        ranked.sort(key=lambda v: float(v["shield_score"]), reverse=True)
        return ranked

    def _action_rationale(self, graph: ReachabilityGraph, plan_steps: Iterable[Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for step in plan_steps:
            out.append(
                {
                    "edge_id": step.edge_id,
                    "action": step.action,
                    "risk_reduction": float(step.risk_before - step.risk_after),
                }
            )
        return out

    def propose(
        self,
        graph: ReachabilityGraph,
        target_risk: float,
        budget: float,
        *,
        case_id: str,
        persist: bool = True,
    ) -> ChangeRequest:
        if len(graph.nodes) > int(self._mrc.get("max_graph_nodes", 10_000)):
            raise GraphTooLargeError(
                f"Graph has {len(graph.nodes)} nodes; increase max_graph_nodes or partition the enclave."
            )

        harden_factor = float(self._mrc.get("harden_factor", 0.08))
        paths_before = graph.top_attack_paths(5)
        risk_before = graph.system_risk()

        mrc_plan = plan_mrc(
            graph,
            budget,
            harden_factor=harden_factor,
            tie_resolver=self._tie_resolver,
        )

        rationale = {
            "summary": (
                f"Greedy MRC reduced aggregate reachability risk from {risk_before:.4f} "
                f"to {mrc_plan.final_risk:.4f} within budget {budget}."
            ),
            "attack_paths_before": paths_before,
            "attack_paths_after_note": "Apply plan actions on graph to compute post-change paths.",
            "per_action_risk_reduction": self._action_rationale(graph, mrc_plan.actions),
            "target_risk": target_risk,
            "met_target": mrc_plan.final_risk <= target_risk + 1e-9,
        }

        after = graph.clone()
        for act in mrc_plan.actions:
            if act.action == "remove":
                after.apply_remove(act.edge_id)
            else:
                after.apply_harden(act.edge_id, harden_factor)
        rationale["attack_paths_after"] = after.top_attack_paths(5)

        max_blast = int(self._planner.get("max_blast_radius", 12))
        change = build_change(
            case_id,
            mrc_plan,
            target_risk=target_risk,
            budget=budget,
            rationale=rationale,
            max_blast_radius=max_blast,
        )

        if persist:
            self.store_change_request(case_id, change)
        return change

    def store_change_request(self, case_id: str, change: ChangeRequest) -> Path:
        case_dir = self.case_storage_dir / str(case_id)
        case_dir.mkdir(parents=True, exist_ok=True)
        out_path = case_dir / "change_request.json"
        out_path.write_text(change.to_json(indent=2), encoding="utf-8")
        return out_path

    def load_change_request(self, case_id: str) -> ChangeRequest:
        path = self.case_storage_dir / str(case_id) / "change_request.json"
        return ChangeRequest.from_json(path.read_text(encoding="utf-8"))
