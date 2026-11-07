"""Abstract twin store interface for Cortex reachability time machine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import networkx as nx

from src.cortex.twin_store.models import (
    EdgeRecord,
    GraphDiff,
    NodeRecord,
    ReachabilityGraph,
    ReachabilityPath,
    SnapshotSource,
)


class TwinStore(ABC):
    """Partitioned, bitemporal graph persistence for operational twin state."""

    @abstractmethod
    def apply_migrations(self, migrations_dir: str | None = None) -> None:
        """Apply numbered SQL migrations for the twin schema."""

    @abstractmethod
    def upsert_snapshot(
        self,
        partition_id: str,
        nodes: list[NodeRecord] | tuple[NodeRecord, ...],
        edges: list[EdgeRecord] | tuple[EdgeRecord, ...],
        source: SnapshotSource,
        *,
        valid_from: datetime | None = None,
        tenant_id: str = "default",
    ) -> None:
        """Close superseded rows and insert a new validity interval for the snapshot."""

    @abstractmethod
    def graph_at(self, partition_id: str, t: datetime, *, tenant_id: str = "default") -> ReachabilityGraph:
        """Materialize partition topology exactly as it was valid at time ``t``."""

    @abstractmethod
    def diff(
        self,
        partition_id: str,
        t1: datetime,
        t2: datetime,
        *,
        tenant_id: str = "default",
    ) -> GraphDiff:
        """Compare node/edge sets between two validity times."""

    @abstractmethod
    def who_could_reach(
        self,
        target: str,
        t: datetime,
        *,
        tenant_id: str = "default",
        partition_id: str | None = None,
    ) -> list[ReachabilityPath]:
        """Return origin-to-target paths with edge evidence at validity time ``t``."""

    @abstractmethod
    def upsert_partition_link(
        self,
        source_partition_id: str,
        target_partition_id: str,
        source: SnapshotSource,
        *,
        link_kind: str = "boundary",
        attributes: dict[str, Any] | None = None,
        valid_from: datetime | None = None,
        tenant_id: str = "default",
    ) -> None:
        """Record a summary link between partitions for cross-segment planning."""

    @abstractmethod
    def partition_summary_graph(
        self, t: datetime, *, tenant_id: str = "default"
    ) -> nx.MultiDiGraph:
        """Return a summary graph of active partition links at time ``t``."""
