"""Shared Cortex test fixtures (CCTV enclave reference topology)."""

from __future__ import annotations

from src.cortex.reachability import MRCReachabilityGraph


def cctv_reachability_graph() -> MRCReachabilityGraph:
    """Reference CCTV / NVR enclave used in cortex regression tests."""
    g = MRCReachabilityGraph(max_graph_nodes=10_000)

    nodes = [
        ("internet", "connector", 0.2),
        ("perimeter_fw", "host", 0.6),
        ("nvr", "host", 0.85),
        ("cam_vlan", "host", 0.7),
        ("ops_station", "host", 0.75),
        ("corp_core", "host", 0.95),
        ("crown_ds", "datastore", 1.0),
    ]
    for nid, kind, crit in nodes:
        g.add_node(nid, kind, criticality=crit)

    edges = [
        ("internet", "perimeter_fw", "connects_to", 0.92, 1.0, 0.4),
        ("perimeter_fw", "nvr", "management", 0.58, 1.0, 0.55),
        ("cam_vlan", "nvr", "connects_to", 1.0, 0.5, 0.1),
        ("ops_station", "nvr", "management", 1.0, 0.5, 0.1),
        ("nvr", "corp_core", "lateral_movement", 0.65, 1.0, 0.45),
        ("corp_core", "crown_ds", "can_access", 0.88, 1.0, 0.35),
    ]
    for src, dst, kind, p, cost, disruption in edges:
        g.add_edge(src, dst, kind, p, cost=cost, disruption=disruption)

    required = [("cam_vlan", "nvr"), ("ops_station", "nvr")]
    g.set_scope(footholds=["internet"], protected=["crown_ds"], required_flows=required)
    return g
