"""Data models for the Cortex bitemporal twin graph store."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import networkx as nx


@dataclass(frozen=True)
class SnapshotSource:
    """Provenance for a twin snapshot ingest (trust affects planner weighting)."""

    name: str
    trust: str


@dataclass(frozen=True)
class NodeRecord:
    """One entity node in a partition snapshot."""

    entity_id: str
    kind: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EdgeRecord:
    """Directed relationship within or across partition boundaries."""

    source: str
    target: str
    kind: str
    attributes: dict[str, Any] = field(default_factory=dict)
    traversal_probability: float | None = None
    required: bool = False
    xiid_resource_id: str | None = None
    is_boundary: bool = False
    boundary_peer_partition_id: str | None = None


@dataclass(frozen=True)
class TwinSnapshot:
    """Nodes and edges submitted together during one ingest."""

    nodes: tuple[NodeRecord, ...]
    edges: tuple[EdgeRecord, ...]


@dataclass
class ReachabilityGraph:
    """In-memory graph view at a validity time; used by planners and networkx."""

    partition_id: str
    as_of: datetime
    graph: nx.MultiDiGraph = field(default_factory=nx.MultiDiGraph)

    def node_ids(self) -> set[str]:
        return set(self.graph.nodes)

    def to_networkx(self) -> nx.MultiDiGraph:
        return self.graph


@dataclass(frozen=True)
class ReachabilityPath:
    """One attacker/source path to a target with edge evidence rows."""

    origin: str
    target: str
    node_path: tuple[str, ...]
    edge_evidence: tuple[dict[str, Any], ...]


@dataclass
class GraphDiff:
    """Structural delta between two validity times in one partition."""

    partition_id: str
    t1: datetime
    t2: datetime
    added_nodes: tuple[str, ...] = ()
    removed_nodes: tuple[str, ...] = ()
    added_edges: tuple[tuple[str, str, str], ...] = ()
    removed_edges: tuple[tuple[str, str, str], ...] = ()
