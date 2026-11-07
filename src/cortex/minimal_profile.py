"""Compute mission-preserving minimal PCCP profiles for suspect twin nodes."""

from __future__ import annotations

from typing import Dict, List, Set

from src.cortex.models import MinimalProfilePlan, PCCPChange
from src.cortex.twin import NetworkTwin


def plan_minimal_profile(twin: NetworkTwin, node: str) -> MinimalProfilePlan:
    """Narrow a suspect node to the smallest edge set that preserves active flows.

    Tactical context:
        Quarantine must not hard-isolate a node when missions still traverse it.
        If no edge set can keep every active flow alive through ``node``, escalate
        to a human reviewer instead of auto-isolating.
    """
    node = str(node)
    flows = twin.partition_mission_flows_at_node(node)
    if not flows:
        return MinimalProfilePlan(
            node=node,
            keep_edges=[],
            narrow_edges=[],
            escalates_to_human=False,
            reason="no active mission flows traverse suspect node",
        )

    keep_ids: Set[str] = set()
    flow_paths: Dict[str, List[str]] = {}
    for flow in flows:
        path = twin.shortest_path_through(flow.source, flow.destination, node)
        if not path:
            return MinimalProfilePlan(
                node=node,
                keep_edges=[],
                narrow_edges=[],
                escalates_to_human=True,
                reason=(
                    f"cannot preserve mission flow {flow.source}->{flow.destination} "
                    f"through {node}"
                ),
            )
        edge_ids = [edge.edge_id for edge in path]
        flow_paths[flow.purpose] = edge_ids
        keep_ids.update(edge_ids)

    narrow: List[PCCPChange] = []
    for edge in twin.incident_edges(node):
        if edge.edge_id in keep_ids:
            continue
        narrow.append(
            PCCPChange(
                action="narrow",
                edge_id=edge.edge_id,
                partition=edge.partition,
                rationale=f"remove non-mission connectivity at suspect node {node}",
            )
        )

    return MinimalProfilePlan(
        node=node,
        keep_edges=sorted(keep_ids),
        narrow_edges=narrow,
        escalates_to_human=False,
        metadata={"flow_paths": flow_paths},
    )
