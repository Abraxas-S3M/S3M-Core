"""PostgreSQL-backed bitemporal twin store (psycopg v3)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx
import psycopg
from psycopg.rows import dict_row

from src.cortex.twin_store.base import TwinStore
from src.cortex.twin_store.models import (
    EdgeRecord,
    GraphDiff,
    NodeRecord,
    ReachabilityGraph,
    ReachabilityPath,
    SnapshotSource,
)

_DEFAULT_MIGRATIONS = Path(__file__).resolve().parents[3] / "scripts" / "storage" / "cortex_twin"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _valid_at_clause() -> str:
    return "(valid_from <= %(as_of)s AND (valid_to IS NULL OR valid_to > %(as_of)s))"


class PostgresTwinStore(TwinStore):
    """Twin store using append-only validity intervals in PostgreSQL."""

    def __init__(self, conninfo: str) -> None:
        if not str(conninfo).strip():
            raise ValueError("conninfo must be non-empty")
        self._conninfo = conninfo

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._conninfo, row_factory=dict_row)

    def apply_migrations(self, migrations_dir: str | None = None) -> None:
        base = Path(migrations_dir) if migrations_dir else _DEFAULT_MIGRATIONS
        if not base.is_dir():
            raise FileNotFoundError(f"migrations directory not found: {base}")
        sql_files = sorted(base.glob("*.sql"))
        with self._connect() as conn:
            with conn.cursor() as cur:
                for path in sql_files:
                    cur.execute(path.read_text(encoding="utf-8"))
            conn.commit()

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
        partition = str(partition_id).strip()
        if not partition:
            raise ValueError("partition_id must be non-empty")
        if not isinstance(source, SnapshotSource):
            raise ValueError("source must be a SnapshotSource")
        vf = valid_from or _utc_now()
        if vf.tzinfo is None:
            vf = vf.replace(tzinfo=timezone.utc)
        recorded = _utc_now()

        incoming_nodes = {n.entity_id for n in nodes}
        incoming_edges = {(e.source, e.target, e.kind) for e in edges}

        with self._connect() as conn:
            with conn.cursor() as cur:
                self._close_nodes_not_in_snapshot(
                    cur, tenant_id, partition, incoming_nodes, vf
                )
                self._close_edges_not_in_snapshot(
                    cur, tenant_id, partition, incoming_edges, vf
                )
                for node in nodes:
                    if not self._node_changed(cur, tenant_id, partition, node):
                        continue
                    self._close_open_node(cur, tenant_id, partition, node.entity_id, vf)
                    cur.execute(
                        """
                        INSERT INTO cortex_twin_nodes (
                            tenant_id, partition_id, entity_id, kind, attributes,
                            valid_from, valid_to, recorded_at, source_name, source_trust
                        ) VALUES (
                            %(tenant_id)s, %(partition_id)s, %(entity_id)s, %(kind)s,
                            %(attributes)s::jsonb, %(valid_from)s, NULL, %(recorded_at)s,
                            %(source_name)s, %(source_trust)s
                        )
                        """,
                        {
                            "tenant_id": tenant_id,
                            "partition_id": partition,
                            "entity_id": node.entity_id,
                            "kind": node.kind,
                            "attributes": json.dumps(node.attributes),
                            "valid_from": vf,
                            "recorded_at": recorded,
                            "source_name": source.name,
                            "source_trust": source.trust,
                        },
                    )
                for edge in edges:
                    if not self._edge_changed(cur, tenant_id, partition, edge):
                        continue
                    self._close_open_edge(
                        cur,
                        tenant_id,
                        partition,
                        edge.source,
                        edge.target,
                        edge.kind,
                        vf,
                    )
                    cur.execute(
                        """
                        INSERT INTO cortex_twin_edges (
                            tenant_id, partition_id, source_entity_id, target_entity_id,
                            kind, attributes, traversal_probability, required,
                            xiid_resource_id, is_boundary, boundary_peer_partition_id,
                            valid_from, valid_to, recorded_at, source_name, source_trust
                        ) VALUES (
                            %(tenant_id)s, %(partition_id)s, %(source)s, %(target)s,
                            %(kind)s, %(attributes)s::jsonb, %(traversal_probability)s,
                            %(required)s, %(xiid_resource_id)s, %(is_boundary)s,
                            %(boundary_peer_partition_id)s,
                            %(valid_from)s, NULL, %(recorded_at)s,
                            %(source_name)s, %(source_trust)s
                        )
                        """,
                        {
                            "tenant_id": tenant_id,
                            "partition_id": partition,
                            "source": edge.source,
                            "target": edge.target,
                            "kind": edge.kind,
                            "attributes": json.dumps(edge.attributes),
                            "traversal_probability": edge.traversal_probability,
                            "required": edge.required,
                            "xiid_resource_id": edge.xiid_resource_id,
                            "is_boundary": edge.is_boundary,
                            "boundary_peer_partition_id": edge.boundary_peer_partition_id,
                            "valid_from": vf,
                            "recorded_at": recorded,
                            "source_name": source.name,
                            "source_trust": source.trust,
                        },
                    )
                    if edge.is_boundary and edge.boundary_peer_partition_id:
                        self._close_partition_link(
                            cur,
                            tenant_id,
                            partition,
                            edge.boundary_peer_partition_id,
                            vf,
                        )
                        cur.execute(
                            """
                            INSERT INTO cortex_twin_partition_links (
                                tenant_id, source_partition_id, target_partition_id,
                                link_kind, attributes, valid_from, valid_to,
                                recorded_at, source_name, source_trust
                            ) VALUES (
                                %(tenant_id)s, %(source_partition)s, %(target_partition)s,
                                'boundary', %(attributes)s::jsonb, %(valid_from)s, NULL,
                                %(recorded_at)s, %(source_name)s, %(source_trust)s
                            )
                            """,
                            {
                                "tenant_id": tenant_id,
                                "source_partition": partition,
                                "target_partition": edge.boundary_peer_partition_id,
                                "attributes": json.dumps(
                                    {"edge_kind": edge.kind, **edge.attributes}
                                ),
                                "valid_from": vf,
                                "recorded_at": recorded,
                                "source_name": source.name,
                                "source_trust": source.trust,
                            },
                        )
            conn.commit()

    def graph_at(self, partition_id: str, t: datetime, *, tenant_id: str = "default") -> ReachabilityGraph:
        as_of = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        graph = nx.MultiDiGraph()
        clause = _valid_at_clause()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT entity_id, kind, attributes
                    FROM cortex_twin_nodes
                    WHERE tenant_id = %(tenant_id)s AND partition_id = %(partition_id)s
                      AND {clause}
                    """,
                    {"tenant_id": tenant_id, "partition_id": partition_id, "as_of": as_of},
                )
                for row in cur.fetchall():
                    graph.add_node(
                        row["entity_id"],
                        kind=row["kind"],
                        attributes=row["attributes"] or {},
                    )
                cur.execute(
                    f"""
                    SELECT source_entity_id, target_entity_id, kind, attributes,
                           traversal_probability, required, xiid_resource_id,
                           is_boundary, boundary_peer_partition_id, recorded_at,
                           source_name, source_trust
                    FROM cortex_twin_edges
                    WHERE tenant_id = %(tenant_id)s AND partition_id = %(partition_id)s
                      AND {clause}
                    """,
                    {"tenant_id": tenant_id, "partition_id": partition_id, "as_of": as_of},
                )
                for row in cur.fetchall():
                    graph.add_edge(
                        row["source_entity_id"],
                        row["target_entity_id"],
                        key=row["kind"],
                        kind=row["kind"],
                        attributes=row["attributes"] or {},
                        traversal_probability=row["traversal_probability"],
                        required=row["required"],
                        xiid_resource_id=row["xiid_resource_id"],
                        is_boundary=row["is_boundary"],
                        boundary_peer_partition_id=row["boundary_peer_partition_id"],
                        recorded_at=row["recorded_at"],
                        source_name=row["source_name"],
                        source_trust=row["source_trust"],
                    )
        return ReachabilityGraph(partition_id=partition_id, as_of=as_of, graph=graph)

    def diff(
        self,
        partition_id: str,
        t1: datetime,
        t2: datetime,
        *,
        tenant_id: str = "default",
    ) -> GraphDiff:
        g1 = self.graph_at(partition_id, t1, tenant_id=tenant_id)
        g2 = self.graph_at(partition_id, t2, tenant_id=tenant_id)
        n1, n2 = g1.node_ids(), g2.node_ids()
        added_nodes = tuple(sorted(n2 - n1))
        removed_nodes = tuple(sorted(n1 - n2))

        def edge_keys(g: ReachabilityGraph) -> set[tuple[str, str, str]]:
            keys: set[tuple[str, str, str]] = set()
            for u, v, data in g.graph.edges(data=True):
                keys.add((str(u), str(v), str(data.get("kind", "related"))))
            return keys

        e1, e2 = edge_keys(g1), edge_keys(g2)
        added_edges = tuple(sorted(e2 - e1))
        removed_edges = tuple(sorted(e1 - e2))
        return GraphDiff(
            partition_id=partition_id,
            t1=t1 if t1.tzinfo else t1.replace(tzinfo=timezone.utc),
            t2=t2 if t2.tzinfo else t2.replace(tzinfo=timezone.utc),
            added_nodes=added_nodes,
            removed_nodes=removed_nodes,
            added_edges=added_edges,
            removed_edges=removed_edges,
        )

    def who_could_reach(
        self,
        target: str,
        t: datetime,
        *,
        tenant_id: str = "default",
        partition_id: str | None = None,
    ) -> list[ReachabilityPath]:
        target_id = str(target).strip()
        if not target_id:
            raise ValueError("target must be non-empty")

        partitions: list[str]
        if partition_id:
            partitions = [partition_id]
        else:
            partitions = self._partitions_containing(tenant_id, target_id, t)

        paths: list[ReachabilityPath] = []
        for pid in partitions:
            view = self.graph_at(pid, t, tenant_id=tenant_id)
            if target_id not in view.graph:
                continue
            reversed_g = view.graph.reverse(copy=False)
            for origin in view.graph.nodes:
                if origin == target_id:
                    continue
                if not nx.has_path(reversed_g, target_id, origin):
                    continue
                # Simple path for evidence (shortest by hop count).
                try:
                    node_path = nx.shortest_path(view.graph, origin, target_id)
                except nx.NetworkXNoPath:
                    continue
                evidence: list[dict[str, Any]] = []
                for idx in range(len(node_path) - 1):
                    u, v = node_path[idx], node_path[idx + 1]
                    edge_data = self._pick_edge_data(view.graph, u, v)
                    evidence.append(
                        {
                            "source": u,
                            "target": v,
                            "partition_id": pid,
                            "as_of": view.as_of.isoformat(),
                            **edge_data,
                        }
                    )
                paths.append(
                    ReachabilityPath(
                        origin=str(origin),
                        target=target_id,
                        node_path=tuple(str(n) for n in node_path),
                        edge_evidence=tuple(evidence),
                    )
                )
        paths.sort(key=lambda p: (len(p.node_path), p.origin))
        return paths

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
        vf = valid_from or _utc_now()
        if vf.tzinfo is None:
            vf = vf.replace(tzinfo=timezone.utc)
        recorded = _utc_now()
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._close_partition_link(cur, tenant_id, source_partition_id, target_partition_id, vf)
                cur.execute(
                    """
                    INSERT INTO cortex_twin_partition_links (
                        tenant_id, source_partition_id, target_partition_id,
                        link_kind, attributes, valid_from, valid_to,
                        recorded_at, source_name, source_trust
                    ) VALUES (
                        %(tenant_id)s, %(source_partition)s, %(target_partition)s,
                        %(link_kind)s, %(attributes)s::jsonb, %(valid_from)s, NULL,
                        %(recorded_at)s, %(source_name)s, %(source_trust)s
                    )
                    """,
                    {
                        "tenant_id": tenant_id,
                        "source_partition": source_partition_id,
                        "target_partition": target_partition_id,
                        "link_kind": link_kind,
                        "attributes": json.dumps(attributes or {}),
                        "valid_from": vf,
                        "recorded_at": recorded,
                        "source_name": source.name,
                        "source_trust": source.trust,
                    },
                )
            conn.commit()

    def partition_summary_graph(self, t: datetime, *, tenant_id: str = "default") -> nx.MultiDiGraph:
        as_of = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        summary = nx.MultiDiGraph()
        clause = _valid_at_clause()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT source_partition_id, target_partition_id, link_kind, attributes
                    FROM cortex_twin_partition_links
                    WHERE tenant_id = %(tenant_id)s AND {clause}
                    """,
                    {"tenant_id": tenant_id, "as_of": as_of},
                )
                for row in cur.fetchall():
                    summary.add_edge(
                        row["source_partition_id"],
                        row["target_partition_id"],
                        key=row["link_kind"],
                        attributes=row["attributes"] or {},
                    )
        return summary

    @staticmethod
    def _pick_edge_data(graph: nx.MultiDiGraph, u: str, v: str) -> dict[str, Any]:
        if graph.has_edge(u, v):
            # MultiDiGraph: take first edge bundle.
            edge_dict = graph.get_edge_data(u, v) or {}
            if edge_dict:
                first_key = next(iter(edge_dict))
                data = dict(edge_dict[first_key])
                data.pop("key", None)
                return data
        return {}

    def _partitions_containing(self, tenant_id: str, entity_id: str, t: datetime) -> list[str]:
        as_of = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        clause = _valid_at_clause()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT DISTINCT partition_id
                    FROM cortex_twin_nodes
                    WHERE tenant_id = %(tenant_id)s AND entity_id = %(entity_id)s
                      AND {clause}
                    """,
                    {"tenant_id": tenant_id, "entity_id": entity_id, "as_of": as_of},
                )
                rows = cur.fetchall()
        return [str(row["partition_id"]) for row in rows]

    @staticmethod
    def _close_nodes_not_in_snapshot(
        cur: psycopg.Cursor,
        tenant_id: str,
        partition_id: str,
        keep: set[str],
        close_at: datetime,
    ) -> None:
        cur.execute(
            """
            SELECT entity_id FROM cortex_twin_nodes
            WHERE tenant_id = %(tenant_id)s
              AND partition_id = %(partition_id)s
              AND valid_to IS NULL
            """,
            {"tenant_id": tenant_id, "partition_id": partition_id},
        )
        for row in cur.fetchall():
            entity_id = row["entity_id"]
            if entity_id not in keep:
                PostgresTwinStore._close_open_node(
                    cur, tenant_id, partition_id, entity_id, close_at
                )

    @staticmethod
    def _close_edges_not_in_snapshot(
        cur: psycopg.Cursor,
        tenant_id: str,
        partition_id: str,
        keep: set[tuple[str, str, str]],
        close_at: datetime,
    ) -> None:
        cur.execute(
            """
            SELECT source_entity_id, target_entity_id, kind
            FROM cortex_twin_edges
            WHERE tenant_id = %(tenant_id)s
              AND partition_id = %(partition_id)s
              AND valid_to IS NULL
            """,
            {"tenant_id": tenant_id, "partition_id": partition_id},
        )
        for row in cur.fetchall():
            key = (row["source_entity_id"], row["target_entity_id"], row["kind"])
            if key not in keep:
                PostgresTwinStore._close_open_edge(
                    cur,
                    tenant_id,
                    partition_id,
                    row["source_entity_id"],
                    row["target_entity_id"],
                    row["kind"],
                    close_at,
                )

    @staticmethod
    def _node_changed(
        cur: psycopg.Cursor, tenant_id: str, partition_id: str, node: NodeRecord
    ) -> bool:
        cur.execute(
            """
            SELECT kind, attributes
            FROM cortex_twin_nodes
            WHERE tenant_id = %(tenant_id)s
              AND partition_id = %(partition_id)s
              AND entity_id = %(entity_id)s
              AND valid_to IS NULL
            """,
            {
                "tenant_id": tenant_id,
                "partition_id": partition_id,
                "entity_id": node.entity_id,
            },
        )
        row = cur.fetchone()
        if row is None:
            return True
        return row["kind"] != node.kind or (row["attributes"] or {}) != node.attributes

    @staticmethod
    def _edge_changed(
        cur: psycopg.Cursor, tenant_id: str, partition_id: str, edge: EdgeRecord
    ) -> bool:
        cur.execute(
            """
            SELECT attributes, traversal_probability, required, xiid_resource_id,
                   is_boundary, boundary_peer_partition_id
            FROM cortex_twin_edges
            WHERE tenant_id = %(tenant_id)s
              AND partition_id = %(partition_id)s
              AND source_entity_id = %(source)s
              AND target_entity_id = %(target)s
              AND kind = %(kind)s
              AND valid_to IS NULL
            """,
            {
                "tenant_id": tenant_id,
                "partition_id": partition_id,
                "source": edge.source,
                "target": edge.target,
                "kind": edge.kind,
            },
        )
        row = cur.fetchone()
        if row is None:
            return True
        return (
            (row["attributes"] or {}) != edge.attributes
            or row["traversal_probability"] != edge.traversal_probability
            or bool(row["required"]) != edge.required
            or row["xiid_resource_id"] != edge.xiid_resource_id
            or bool(row["is_boundary"]) != edge.is_boundary
            or row["boundary_peer_partition_id"] != edge.boundary_peer_partition_id
        )

    @staticmethod
    def _close_open_node(
        cur: psycopg.Cursor,
        tenant_id: str,
        partition_id: str,
        entity_id: str,
        close_at: datetime,
    ) -> None:
        cur.execute(
            """
            UPDATE cortex_twin_nodes
            SET valid_to = %(close_at)s
            WHERE tenant_id = %(tenant_id)s
              AND partition_id = %(partition_id)s
              AND entity_id = %(entity_id)s
              AND valid_to IS NULL
            """,
            {
                "tenant_id": tenant_id,
                "partition_id": partition_id,
                "entity_id": entity_id,
                "close_at": close_at,
            },
        )

    @staticmethod
    def _close_open_edge(
        cur: psycopg.Cursor,
        tenant_id: str,
        partition_id: str,
        source: str,
        target: str,
        kind: str,
        close_at: datetime,
    ) -> None:
        cur.execute(
            """
            UPDATE cortex_twin_edges
            SET valid_to = %(close_at)s
            WHERE tenant_id = %(tenant_id)s
              AND partition_id = %(partition_id)s
              AND source_entity_id = %(source)s
              AND target_entity_id = %(target)s
              AND kind = %(kind)s
              AND valid_to IS NULL
            """,
            {
                "tenant_id": tenant_id,
                "partition_id": partition_id,
                "source": source,
                "target": target,
                "kind": kind,
                "close_at": close_at,
            },
        )

    @staticmethod
    def _close_partition_link(
        cur: psycopg.Cursor,
        tenant_id: str,
        source_partition: str,
        target_partition: str,
        close_at: datetime,
    ) -> None:
        cur.execute(
            """
            UPDATE cortex_twin_partition_links
            SET valid_to = %(close_at)s
            WHERE tenant_id = %(tenant_id)s
              AND source_partition_id = %(source_partition)s
              AND target_partition_id = %(target_partition)s
              AND valid_to IS NULL
            """,
            {
                "tenant_id": tenant_id,
                "source_partition": source_partition,
                "target_partition": target_partition,
                "close_at": close_at,
            },
        )
