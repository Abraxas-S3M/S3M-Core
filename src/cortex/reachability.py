"""Attack-path reachability graph and minimum-risk change (MRC) planning.

Military/tactical context: models how an adversary moves from external footholds
toward mission-critical assets so defenders can prioritize hardening without
breaking required operational flows (e.g. CCTV ingest, operator access).
"""

from __future__ import annotations

import copy
import heapq
import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from src.autonomy.decision_engine.multi_objective import ParetoOptimizer

LOG_FLOOR = math.log(1e-15)


class GraphTooLargeError(RuntimeError):
    """Raised when the reachability graph exceeds configured limits."""


@dataclass
class RGNode:
    node_id: str
    kind: str
    criticality: float = 0.5
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RGEdge:
    edge_id: str
    source: str
    target: str
    kind: str
    p: float
    cost: float = 1.0
    disruption: float = 0.3
    removed: bool = False
    hardened: bool = False

    @property
    def effective_p(self) -> float:
        if self.removed:
            return 0.0
        return max(0.0, min(1.0, float(self.p)))


@dataclass
class MRCAction:
    edge_id: str
    action: str
    cost: float
    disruption: float
    risk_before: float
    risk_after: float

    @property
    def risk_delta(self) -> float:
        return self.risk_before - self.risk_after


@dataclass
class MRCPlan:
    actions: List[MRCAction]
    initial_risk: float
    final_risk: float
    budget_spent: float
    required_flows_ok: bool


class MRCReachabilityGraph:
    """Directed probabilistic reachability graph for attack-path analysis."""

    def __init__(
        self,
        *,
        max_graph_nodes: int = 10_000,
    ) -> None:
        self.nodes: Dict[str, RGNode] = {}
        self.edges: Dict[str, RGEdge] = {}
        self._out: Dict[str, List[str]] = {}
        self.footholds: Set[str] = set()
        self.protected: Set[str] = set()
        self.required_flows: List[Tuple[str, str]] = []
        self.max_graph_nodes = max(1, int(max_graph_nodes))
        self._path_cache: Dict[str, Tuple[Dict[str, float], Dict[str, Tuple[str, str]]]] = {}

    def add_node(self, node_id: str, kind: str, criticality: float = 0.5, **attrs: Any) -> None:
        if len(self.nodes) >= self.max_graph_nodes:
            raise GraphTooLargeError(
                f"Graph has {len(self.nodes)} nodes (limit {self.max_graph_nodes}). "
                "Partition the knowledge graph by enclave or mission slice before planning."
            )
        self.nodes[node_id] = RGNode(node_id=node_id, kind=kind, criticality=criticality, attrs=dict(attrs))
        self._out.setdefault(node_id, [])
        self._path_cache.clear()

    def add_edge(
        self,
        source: str,
        target: str,
        kind: str,
        p: float,
        *,
        edge_id: str | None = None,
        cost: float = 1.0,
        disruption: float = 0.3,
    ) -> str:
        if source not in self.nodes or target not in self.nodes:
            raise KeyError("source and target must exist before adding an edge")
        eid = edge_id or f"{source}->{target}:{kind}:{uuid.uuid4().hex[:8]}"
        self.edges[eid] = RGEdge(
            edge_id=eid,
            source=source,
            target=target,
            kind=kind,
            p=float(p),
            cost=float(cost),
            disruption=float(disruption),
        )
        self._out.setdefault(source, []).append(eid)
        self._path_cache.clear()
        return eid

    def set_scope(
        self,
        footholds: Iterable[str],
        protected: Iterable[str],
        required_flows: Iterable[Tuple[str, str]],
    ) -> None:
        self.footholds = {str(x) for x in footholds}
        self.protected = {str(x) for x in protected}
        self.required_flows = [(str(a), str(b)) for a, b in required_flows]
        self._path_cache.clear()

    def clone(self) -> MRCReachabilityGraph:
        other = MRCReachabilityGraph(max_graph_nodes=self.max_graph_nodes)
        other.nodes = copy.deepcopy(self.nodes)
        other.edges = copy.deepcopy(self.edges)
        other._out = copy.deepcopy(self._out)
        other.footholds = set(self.footholds)
        other.protected = set(self.protected)
        other.required_flows = list(self.required_flows)
        return other

    def _paths_from(self, source: str) -> Tuple[Dict[str, float], Dict[str, Tuple[str, str]]]:
        if source in self._path_cache:
            return self._path_cache[source]

        best_log: Dict[str, float] = {source: 0.0}
        pred: Dict[str, Tuple[str, str]] = {}
        heap: List[Tuple[float, str]] = [(0.0, source)]

        while heap:
            neg_log_p, node = heapq.heappop(heap)
            cur = -neg_log_p
            if cur < best_log.get(node, float("-inf")) - 1e-12:
                continue
            for eid in self._out.get(node, []):
                edge = self.edges[eid]
                ep = edge.effective_p
                if ep <= 0.0:
                    continue
                nxt = edge.target
                new_log = cur + math.log(max(ep, 1e-15))
                if new_log > best_log.get(nxt, float("-inf")) + 1e-12:
                    best_log[nxt] = new_log
                    pred[nxt] = (node, eid)
                    heapq.heappush(heap, (-new_log, nxt))

        self._path_cache[source] = (best_log, pred)
        return best_log, pred

    def invalidate_paths_for_footholds(self, footholds: Iterable[str]) -> None:
        for f in footholds:
            self._path_cache.pop(f, None)

    def path_uses_edge(self, source: str, target: str, edge_id: str) -> bool:
        _, pred = self._paths_from(source)
        cur = target
        visited: Set[str] = set()
        while cur in pred and cur not in visited:
            visited.add(cur)
            prev, eid = pred[cur]
            if eid == edge_id:
                return True
            cur = prev
        return False

    def max_path_prob(self, source: str, target: str) -> float:
        best_log, _ = self._paths_from(source)
        lp = best_log.get(target, float("-inf"))
        if lp == float("-inf"):
            return 0.0
        return float(math.exp(lp))

    def system_risk(self) -> float:
        """Aggregate probability an adversary reaches any protected asset."""
        path_probs: List[float] = []
        for foot in self.footholds:
            for prot in self.protected:
                path_probs.append(self.max_path_prob(foot, prot))
        if not path_probs:
            return 0.0
        survival = 1.0
        for p in path_probs:
            survival *= 1.0 - min(1.0, max(0.0, p))
        return 1.0 - survival

    def top_attack_paths(self, limit: int = 5) -> List[Dict[str, Any]]:
        scored: List[Tuple[float, str, str, List[str]]] = []
        for foot in self.footholds:
            _, pred = self._paths_from(foot)
            for prot in self.protected:
                prob = self.max_path_prob(foot, prot)
                if prob <= 0.0:
                    continue
                nodes_path: List[str] = []
                cur = prot
                visited: Set[str] = set()
                while cur != foot and cur in pred and cur not in visited:
                    visited.add(cur)
                    nodes_path.append(cur)
                    cur, _ = pred[cur]
                nodes_path.append(foot)
                nodes_path.reverse()
                scored.append((prob, foot, prot, nodes_path))
        scored.sort(key=lambda item: item[0], reverse=True)
        out: List[Dict[str, Any]] = []
        for prob, foot, prot, nodes_path in scored[:limit]:
            out.append(
                {
                    "foothold": foot,
                    "protected": prot,
                    "probability": prob,
                    "nodes": nodes_path,
                }
            )
        return out

    def required_flows_reachable(self) -> bool:
        for src, dst in self.required_flows:
            if self.max_path_prob(src, dst) <= 0.0:
                return False
        return True

    def apply_harden(self, edge_id: str, factor: float) -> None:
        edge = self.edges[edge_id]
        if edge.hardened:
            return
        edge.p = edge.p * factor
        edge.hardened = True
        affected: Set[str] = set()
        for foot in self.footholds:
            if any(self.path_uses_edge(foot, prot, edge_id) for prot in self.protected):
                affected.add(foot)
        self.invalidate_paths_for_footholds(affected)

    def apply_remove(self, edge_id: str) -> None:
        self.edges[edge_id].removed = True
        affected: Set[str] = set()
        for foot in self.footholds:
            if any(self.path_uses_edge(foot, prot, edge_id) for prot in self.protected):
                affected.add(foot)
        self.invalidate_paths_for_footholds(affected)

    def edges_on_attack_paths(self) -> Set[str]:
        """Edges that appear on a current max-probability path to any protected asset."""
        on_path: Set[str] = set()
        for foot in self.footholds:
            _, pred = self._paths_from(foot)
            for prot in self.protected:
                if self.max_path_prob(foot, prot) <= 0.0:
                    continue
                cur = prot
                visited: Set[str] = set()
                while cur in pred and cur not in visited:
                    visited.add(cur)
                    prev, eid = pred[cur]
                    on_path.add(eid)
                    cur = prev
        return on_path

    def candidate_actions(
        self,
        harden_factor: float,
        *,
        attack_path_only: bool = True,
    ) -> List[Tuple[str, str, float, float]]:
        """Return (edge_id, kind, cost, disruption) for harden/remove."""
        allowed = self.edges_on_attack_paths() if attack_path_only else None
        items: List[Tuple[str, str, float, float]] = []
        for eid, edge in self.edges.items():
            if allowed is not None and eid not in allowed:
                continue
            if edge.removed or edge.hardened or edge.effective_p <= 0.0:
                continue
            items.append((eid, "harden", edge.cost, edge.disruption))
            items.append((eid, "remove", edge.cost * 1.25, edge.disruption * 1.15))
        _ = harden_factor
        return items


def _evaluate_action(
    graph: MRCReachabilityGraph,
    edge_id: str,
    kind: str,
    harden_factor: float,
) -> Tuple[float, bool]:
    """Simulate an action with rollback; re-dijkstra only for affected footholds."""
    edge = graph.edges[edge_id]
    snap = (edge.p, edge.removed, edge.hardened)
    affected: Set[str] = set()
    for foot in graph.footholds:
        if any(graph.path_uses_edge(foot, prot, edge_id) for prot in graph.protected):
            affected.add(foot)

    if kind == "remove":
        edge.removed = True
    elif edge.hardened:
        graph.invalidate_paths_for_footholds(affected)
        return graph.system_risk(), graph.required_flows_reachable()
    else:
        edge.p = edge.p * harden_factor
        edge.hardened = True

    graph.invalidate_paths_for_footholds(affected)
    risk_after = graph.system_risk()
    flows_ok = graph.required_flows_reachable()

    edge.p, edge.removed, edge.hardened = snap
    graph.invalidate_paths_for_footholds(affected)
    return risk_after, flows_ok


def _pick_best_candidate(
    graph: MRCReachabilityGraph,
    budget_remaining: float,
    harden_factor: float,
    tie_resolver: ParetoOptimizer | None,
) -> MRCAction | None:
    risk_before = graph.system_risk()
    best: MRCAction | None = None
    equal_gain: Dict[str, Dict[str, float]] = {}
    candidate_meta: Dict[str, Tuple[str, str, float, float]] = {}

    for eid, kind, cost, disruption in graph.candidate_actions(harden_factor):
        if cost > budget_remaining + 1e-9:
            continue
        risk_after, flows_ok = _evaluate_action(graph, eid, kind, harden_factor)
        if not flows_ok:
            continue
        if kind == "remove" and risk_before > 1e-9 and risk_after <= 1e-9:
            continue
        gain = risk_before - risk_after
        if gain <= 1e-12:
            continue
        key = f"{kind}:{eid}"
        candidate_meta[key] = (eid, kind, cost, disruption)
        equal_gain[key] = {
            "survival": gain,
            "mission_progress": gain,
            "roe_risk": disruption,
            "fuel_cost": cost,
            "info_gain": 0.0,
        }
        action = MRCAction(
            edge_id=eid,
            action=kind,
            cost=cost,
            disruption=disruption,
            risk_before=risk_before,
            risk_after=risk_after,
        )
        if best is None or gain > best.risk_delta + 1e-12:
            best = action
        elif abs(gain - best.risk_delta) <= 1e-9:
            if best is not None:
                prev_key = f"{best.action}:{best.edge_id}"
                if prev_key not in equal_gain:
                    equal_gain[prev_key] = {
                        "survival": best.risk_delta,
                        "mission_progress": best.risk_delta,
                        "roe_risk": best.disruption,
                        "fuel_cost": best.cost,
                        "info_gain": 0.0,
                    }

    if best is None:
        return None

    tied = [k for k, v in equal_gain.items() if abs(v["survival"] - best.risk_delta) <= 1e-9]
    if len(tied) > 1 and tie_resolver is not None:
        subset = {k: equal_gain[k] for k in tied}
        chosen, _, _ = tie_resolver.select_action(subset, method="topsis", fallback=tied[0])
        eid, kind, cost, disruption = candidate_meta[chosen]
        risk_after, _ = _evaluate_action(graph, eid, kind, harden_factor)
        return MRCAction(
            edge_id=eid,
            action=kind,
            cost=cost,
            disruption=disruption,
            risk_before=risk_before,
            risk_after=risk_after,
        )

    if best is not None and len(tied) > 1:
        tied.sort(key=lambda k: (equal_gain[k]["roe_risk"], equal_gain[k]["fuel_cost"], k))
        chosen = tied[0]
        eid, kind, cost, disruption = candidate_meta[chosen]
        risk_after, _ = _evaluate_action(graph, eid, kind, harden_factor)
        return MRCAction(
            edge_id=eid,
            action=kind,
            cost=cost,
            disruption=disruption,
            risk_before=risk_before,
            risk_after=risk_after,
        )
    return best


def plan_mrc_reference(
    graph: MRCReachabilityGraph,
    budget: float,
    *,
    harden_factor: float = 0.08,
    tie_resolver: ParetoOptimizer | None = None,
) -> MRCPlan:
    """Naive greedy MRC: full path recomputation each iteration (reference)."""
    working = graph.clone()
    working._path_cache.clear()
    spent = 0.0
    actions: List[MRCAction] = []
    initial = working.system_risk()

    while spent < budget - 1e-9:
        working._path_cache.clear()
        pick = _pick_best_candidate(working, budget - spent, harden_factor, tie_resolver)
        if pick is None:
            break
        if pick.action == "remove":
            working.apply_remove(pick.edge_id)
        else:
            working.apply_harden(pick.edge_id, harden_factor)
        actions.append(pick)
        spent += pick.cost

    return MRCPlan(
        actions=actions,
        initial_risk=initial,
        final_risk=working.system_risk(),
        budget_spent=spent,
        required_flows_ok=working.required_flows_reachable(),
    )


def plan_mrc(
    graph: MRCReachabilityGraph,
    budget: float,
    *,
    harden_factor: float = 0.08,
    tie_resolver: ParetoOptimizer | None = None,
) -> MRCPlan:
    """Greedy MRC with incremental path-cache invalidation per foothold."""
    working = graph.clone()
    spent = 0.0
    actions: List[MRCAction] = []
    initial = working.system_risk()

    while spent < budget - 1e-9:
        pick = _pick_best_candidate(working, budget - spent, harden_factor, tie_resolver)
        if pick is None:
            break
        if pick.action == "remove":
            working.apply_remove(pick.edge_id)
        else:
            working.apply_harden(pick.edge_id, harden_factor)
        actions.append(pick)
        spent += pick.cost

    return MRCPlan(
        actions=actions,
        initial_risk=initial,
        final_risk=working.system_risk(),
        budget_spent=spent,
        required_flows_ok=working.required_flows_reachable(),
    )


def shield_priority(
    vuln: Dict[str, Any],
    *,
    reachability_score: float,
    weights: Dict[str, float] | None = None,
) -> float:
    """Rank vulnerability for shield queue (higher = patch sooner)."""
    w = {
        "epss": 0.30,
        "kev": 0.25,
        "reachability": 0.20,
        "criticality": 0.15,
        "days_to_patch": 0.10,
    }
    if weights:
        w.update(weights)

    epss = max(0.0, min(1.0, float(vuln.get("epss", 0.0))))
    kev = 1.0 if vuln.get("kev") or vuln.get("in_kev") else 0.0
    crit = max(0.0, min(1.0, float(vuln.get("criticality", 0.5))))
    days = max(0.0, float(vuln.get("days_to_patch", 30.0)))
    patch_urgency = 1.0 - min(1.0, days / 90.0)
    reach = max(0.0, min(1.0, float(reachability_score)))

    return (
        w["epss"] * epss
        + w["kev"] * kev
        + w["reachability"] * reach
        + w["criticality"] * crit
        + w["days_to_patch"] * patch_urgency
    )


def random_small_graph(
    rng,
    *,
    n_nodes: int = 12,
    edge_prob: float = 0.25,
    max_graph_nodes: int = 10_000,
) -> MRCReachabilityGraph:
    """Generate a small random acyclic-ish graph for property tests."""
    g = MRCReachabilityGraph(max_graph_nodes=max_graph_nodes)
    for i in range(n_nodes):
        g.add_node(f"n{i}", "host", criticality=rng.random())
    for i in range(n_nodes):
        for j in range(i + 1, n_nodes):
            if rng.random() < edge_prob:
                g.add_edge(f"n{i}", f"n{j}", "connects_to", p=0.2 + 0.6 * rng.random())
    foothold = "n0"
    protected = {f"n{n_nodes - 1}"}
    flows = []
    if n_nodes > 2:
        flows.append((f"n{n_nodes // 2}", f"n{n_nodes // 2 + 1}"))
    g.set_scope([foothold], protected, flows)
    return g


def synthetic_graph(
    n_nodes: int,
    *,
    out_degree: int = 4,
    max_graph_nodes: int = 10_000,
    seed: int = 0,
) -> MRCReachabilityGraph:
    """Layered synthetic graph for performance smoke tests."""
    import random

    rng = random.Random(seed)
    g = MRCReachabilityGraph(max_graph_nodes=max_graph_nodes)
    layers = max(2, int(math.sqrt(n_nodes)))
    per_layer = max(1, n_nodes // layers)
    node_ids: List[str] = []
    for layer in range(layers):
        for i in range(per_layer):
            if len(node_ids) >= n_nodes:
                break
            nid = f"L{layer}N{i}"
            kind = "host" if layer else "connector"
            g.add_node(nid, kind, criticality=0.3 + 0.5 * (layer / max(1, layers - 1)))
            node_ids.append(nid)

    for idx, src in enumerate(node_ids):
        for _ in range(out_degree):
            tgt = rng.choice(node_ids[idx + 1 :] or node_ids)
            if src == tgt:
                continue
            g.add_edge(src, tgt, "lateral_movement", p=0.15 + 0.5 * rng.random(), cost=1.0)

    g.set_scope([node_ids[0]], [node_ids[-1]], [(node_ids[len(node_ids) // 2], node_ids[len(node_ids) // 2 + 1])])
    return g
