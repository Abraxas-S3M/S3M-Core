"""S3M CyberTwin: attack-path digital twin built from observed XiiD state.

Military/tactical context:
The twin is rebuilt from what the XiiD control plane *reports* (routes, findings,
STLinks) plus Abraxas mission context XiiD does not hold (protected assets, required
business flows, identity exposure). Because it is rebuilt from observation, the same
code serves planning ("what if") and verification ("what actually happened").

Modelling assumptions (documented, tunable, not validated against live XiiD):

* Hosts are compressed into equivalence classes (a user group, one node per server).
* Route edge probability = 1 - prod(1 - exploit_p(f)) over findings on the target that
  match the route's service; otherwise a baseline (higher for admin protocols).
* A route marked ``sealed_tunnel`` is scaled by ``SEALED_FACTOR``. REQUIRES XIID
  VALIDATION: this encodes a claimed property of SealedTunnel, not a measured one.
* Narrowing a route's source prefix scales its edge by ``NARROW_FACTOR``.
* Identity edges (cached admin credentials, domain control) are never actionable through
  XiiD route tools; the twin keeps them so residual risk is reported honestly.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from src.cortex.reachability import MRCReachabilityGraph, shield_priority

NARROW_FACTOR = 0.08  # matches plan_mrc default harden_factor
SEALED_FACTOR = 0.10
ADMIN_SERVICES = frozenset({"ssh", "rdp", "smb", "ldap", "any", "winrm"})
BASELINE_ADMIN_P = 0.12
BASELINE_P = 0.03
MAX_P = 0.95


def exploit_probability(finding: Mapping[str, Any]) -> float:
    """Heuristic single-step exploitation likelihood from CVSS, EPSS and KEV."""
    cvss = max(0.0, min(10.0, float(finding.get("cvss", 5.0))))
    epss = max(0.0, min(1.0, float(finding.get("epss", 0.0))))
    kev = 1.0 if finding.get("kev") else 0.0
    return max(0.0, min(MAX_P, 0.10 + 0.30 * cvss / 10.0 + 0.40 * epss + 0.15 * kev))


@dataclass
class RouteEdgeMeta:
    route_id: str
    source: str
    target: str
    service: str
    original_prefix: str
    narrow_candidate: Optional[str]
    observed_sessions_30d: int
    sealed: bool
    required_by: List[str] = field(default_factory=list)
    status: str = "active"
    narrowed_to: Optional[str] = None

    @property
    def is_narrowed(self) -> bool:
        return bool(self.narrowed_to) and self.narrowed_to != self.original_prefix


class CyberTwinGraph(MRCReachabilityGraph):
    """Reachability graph whose actions map 1:1 onto XiiD route tools.

    Overrides the base graph so that:
    * only XiiD routes are actionable (identity edges are not),
    * ``harden`` is offered only where a narrower source prefix exists,
    * ``remove`` (expire) is never offered for a route a required flow depends on,
    * required flows are satisfied only by their own route staying active.
    """

    EXPIRE_POLICIES = ("any", "unused_only", "none")

    def __init__(self, *, max_graph_nodes: int = 10_000, expire_policy: str = "any") -> None:
        if expire_policy not in self.EXPIRE_POLICIES:
            raise ValueError(f"expire_policy must be one of {self.EXPIRE_POLICIES}")
        super().__init__(max_graph_nodes=max_graph_nodes)
        self.route_meta: Dict[str, RouteEdgeMeta] = {}  # edge_id -> meta
        self.route_edge: Dict[str, str] = {}  # route_id -> edge_id
        self.flow_routes: Dict[str, str] = {}  # flow_id -> route_id
        # any: expire any non-required route; unused_only: only routes with zero observed
        # sessions (minimal disruption); none: reversible narrowing only.
        self.expire_policy = expire_policy

    # ---- MRC overrides -------------------------------------------------
    def clone(self) -> "CyberTwinGraph":
        other = CyberTwinGraph(max_graph_nodes=self.max_graph_nodes, expire_policy=self.expire_policy)
        other.nodes = copy.deepcopy(self.nodes)
        other.edges = copy.deepcopy(self.edges)
        other._out = copy.deepcopy(self._out)
        other.footholds = set(self.footholds)
        other.protected = set(self.protected)
        other.required_flows = list(self.required_flows)
        other.route_meta = copy.deepcopy(self.route_meta)
        other.route_edge = dict(self.route_edge)
        other.flow_routes = dict(self.flow_routes)
        return other

    def required_flows_reachable(self) -> bool:
        return not self.broken_flows()

    def candidate_actions(
        self,
        harden_factor: float,
        *,
        attack_path_only: bool = True,
    ) -> List[Tuple[str, str, float, float]]:
        allowed = self.edges_on_attack_paths() if attack_path_only else None
        items: List[Tuple[str, str, float, float]] = []
        for eid, meta in self.route_meta.items():
            edge = self.edges[eid]
            if allowed is not None and eid not in allowed:
                continue
            if edge.removed or edge.effective_p <= 0.0:
                continue
            if meta.narrow_candidate and not edge.hardened and not meta.is_narrowed:
                items.append((eid, "harden", edge.cost, edge.disruption))
            if self._may_expire(meta):
                items.append((eid, "remove", edge.cost * 1.25, edge.disruption * 1.15))
        _ = harden_factor
        return items

    def _may_expire(self, meta: RouteEdgeMeta) -> bool:
        if meta.required_by or self.expire_policy == "none":
            return False
        if self.expire_policy == "unused_only":
            return meta.observed_sessions_30d == 0
        return True

    def with_policy(self, expire_policy: str) -> "CyberTwinGraph":
        other = self.clone()
        if expire_policy not in self.EXPIRE_POLICIES:
            raise ValueError(f"expire_policy must be one of {self.EXPIRE_POLICIES}")
        other.expire_policy = expire_policy
        return other

    # ---- twin queries --------------------------------------------------
    def broken_flows(self) -> List[str]:
        broken = []
        for flow_id, route_id in self.flow_routes.items():
            eid = self.route_edge.get(route_id)
            if eid is None or self.edges[eid].removed:
                broken.append(flow_id)
        return sorted(broken)

    def unnecessary_routes(self) -> List[RouteEdgeMeta]:
        """Active routes with no observed use and no dependent required flow (SIM-001)."""
        out = []
        for eid, meta in self.route_meta.items():
            if self.edges[eid].removed:
                continue
            if meta.observed_sessions_30d == 0 and not meta.required_by:
                out.append(meta)
        return sorted(out, key=lambda m: m.route_id)

    def route_risk_contribution(self) -> Dict[str, float]:
        """Risk reduction if each route alone were expired (ignores required-flow rules)."""
        base = self.system_risk()
        out: Dict[str, float] = {}
        for route_id, eid in self.route_edge.items():
            edge = self.edges[eid]
            if edge.removed:
                continue
            snap = edge.removed
            edge.removed = True
            self._path_cache.clear()
            out[route_id] = base - self.system_risk()
            edge.removed = snap
            self._path_cache.clear()
        return out

    def summary(self) -> Dict[str, Any]:
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "routes": len(self.route_meta),
            "identity_edges": len(self.edges) - len(self.route_meta),
            "footholds": sorted(self.footholds),
            "protected": sorted(self.protected),
            "system_risk": round(self.system_risk(), 6),
            "broken_flows": self.broken_flows(),
        }


def _route_probability(route: Mapping[str, Any], findings_by_host: Mapping[str, List[Mapping[str, Any]]]) -> float:
    service = str(route.get("service", ""))
    matched = [
        f
        for f in findings_by_host.get(str(route.get("target")), [])
        if str(f.get("service")) in (service, "any") or service == "any"
    ]
    if matched:
        survive = 1.0
        for f in matched:
            survive *= 1.0 - exploit_probability(f)
        p = 1.0 - survive
    else:
        p = BASELINE_ADMIN_P if service in ADMIN_SERVICES else BASELINE_P
    if route.get("sealed_tunnel"):
        p *= SEALED_FACTOR
    return max(0.0, min(MAX_P, p))


def _route_disruption(route: Mapping[str, Any]) -> float:
    used = max(0, int(route.get("observed_sessions_30d", 0)))
    return round(min(1.0, math.log10(1 + used) / 7.0), 6)


def build_twin(
    routes: Iterable[Mapping[str, Any]],
    findings: Iterable[Mapping[str, Any]],
    mission: Mapping[str, Any],
    *,
    expire_policy: str = "any",
) -> CyberTwinGraph:
    """Construct the twin from XiiD inventory reads plus mission context."""
    routes = [dict(r) for r in routes]
    findings = [dict(f) for f in findings]
    by_host: Dict[str, List[Mapping[str, Any]]] = {}
    for f in findings:
        by_host.setdefault(str(f.get("host") or f.get("component")), []).append(f)

    protected = dict(mission.get("protected_assets", {}))
    footholds = list(mission.get("footholds", []))
    flow_routes = {str(fl["id"]): str(fl["route"]) for fl in mission.get("required_flows", [])}
    required_by: Dict[str, List[str]] = {}
    for flow_id, route_id in flow_routes.items():
        required_by.setdefault(route_id, []).append(flow_id)

    g = CyberTwinGraph(expire_policy=expire_policy)
    node_ids: Set[str] = set(footholds) | set(protected)
    for r in routes:
        node_ids.update((str(r["source"]), str(r["target"])))
    for e in mission.get("identity_edges", []):
        node_ids.update((str(e["source"]), str(e["target"])))
    for nid in sorted(node_ids):
        kind = nid.split(":", 1)[0] if ":" in nid else "server"
        g.add_node(nid, kind, criticality=1.0 if nid in protected else 0.4)

    for r in sorted(routes, key=lambda x: str(x["id"])):
        rid = str(r["id"])
        status = str(r.get("status", "active"))
        narrowed_to = r.get("narrow_to")
        meta = RouteEdgeMeta(
            route_id=rid,
            source=str(r["source"]),
            target=str(r["target"]),
            service=str(r.get("service", "")),
            original_prefix=str(r.get("prefix", "")),
            narrow_candidate=r.get("narrow_candidate"),
            observed_sessions_30d=int(r.get("observed_sessions_30d", 0)),
            sealed=bool(r.get("sealed_tunnel")),
            required_by=sorted(required_by.get(rid, [])),
            status=status,
            narrowed_to=narrowed_to,
        )
        eid = g.add_edge(
            meta.source,
            meta.target,
            "route",
            p=_route_probability(r, by_host),
            edge_id=f"route:{rid}",
            cost=1.0,
            disruption=_route_disruption(r),
        )
        edge = g.edges[eid]
        if status == "expired":
            edge.removed = True
        elif meta.is_narrowed:
            edge.p *= NARROW_FACTOR
            edge.hardened = True
        g.route_meta[eid] = meta
        g.route_edge[rid] = eid

    for i, e in enumerate(mission.get("identity_edges", [])):
        g.add_edge(
            str(e["source"]),
            str(e["target"]),
            f"identity:{e.get('kind', 'credential')}",
            p=float(e.get("p", 0.3)),
            edge_id=f"identity:{i}:{e['source']}->{e['target']}",
            cost=1e9,
        )

    g.flow_routes = flow_routes
    g.set_scope(footholds, protected.keys(), [])
    return g


def prioritized_findings(twin: CyberTwinGraph, findings: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Rank findings by the existing shield priority, using twin reachability."""
    ranked = []
    for f in findings:
        host = str(f.get("host") or f.get("component"))
        reach = max((twin.max_path_prob(ft, host) for ft in twin.footholds if host in twin.nodes), default=0.0)
        crit = 1.0 if host in twin.protected else 0.4
        score = shield_priority(
            {"epss": f.get("epss", 0.0), "kev": f.get("kev"), "criticality": crit, "days_to_patch": 30},
            reachability_score=reach,
        )
        ranked.append({**dict(f), "reachability": round(reach, 6), "priority": round(score, 6)})
    ranked.sort(key=lambda x: x["priority"], reverse=True)
    return ranked
