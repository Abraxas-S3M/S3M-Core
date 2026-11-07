"""Load bitemporal twin snapshots into the in-memory S3M knowledge graph."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from s3m_core.memory.knowledge_graph import S3MKnowledgeGraph

from src.cortex.twin_store.base import TwinStore
from src.cortex.twin_store.models import ReachabilityGraph

_KG_ENTITY_MAP = {
    "person": "person",
    "organization": "organization",
    "system": "system",
    "tool": "tool",
    "concept": "concept",
    "vulnerability": "vulnerability",
    "document": "document",
    "codebase": "codebase",
    "service": "service",
}

_KG_RELATION_MAP = {
    "uses": "uses",
    "depends_on": "depends_on",
    "related_to": "related_to",
    "part_of": "part_of",
    "discovered_by": "discovered_by",
    "solved_with": "solved_with",
    "caused_by": "caused_by",
    "network_route": "depends_on",
    "connects_to": "related_to",
}


class TwinStoreKnowledgeAdapter:
    """Bridge Cortex twin partitions into ``S3MKnowledgeGraph`` for mission planning."""

    def __init__(self, store: TwinStore) -> None:
        self._store = store

    def load_snapshot(
        self,
        graph: S3MKnowledgeGraph,
        partition_id: str,
        t: datetime,
        *,
        tenant_id: str = "default",
        prefix_entities: bool = True,
    ) -> ReachabilityGraph:
        """Merge a partition-valid view into an existing knowledge graph instance."""

        view = self._store.graph_at(partition_id, t, tenant_id=tenant_id)
        for node_id, data in view.graph.nodes(data=True):
            entity_id = self._entity_key(partition_id, node_id, prefix_entities)
            entity_type = self._map_entity_type(str(data.get("kind", "system")))
            attributes: dict[str, Any] = dict(data.get("attributes") or {})
            attributes["partition_id"] = partition_id
            attributes["twin_valid_as_of"] = view.as_of.isoformat()
            graph.add_entity(entity_id, entity_type, attributes)

        for source, target, edge_data in view.graph.edges(data=True):
            src = self._entity_key(partition_id, source, prefix_entities)
            tgt = self._entity_key(partition_id, target, prefix_entities)
            relation = self._map_relation(str(edge_data.get("kind", "related_to")))
            metadata: dict[str, Any] = dict(edge_data.get("attributes") or {})
            metadata["partition_id"] = partition_id
            if edge_data.get("traversal_probability") is not None:
                metadata["traversal_probability"] = edge_data["traversal_probability"]
            if edge_data.get("xiid_resource_id"):
                metadata["xiid_resource_id"] = edge_data["xiid_resource_id"]
            graph.add_relationship(src, tgt, relation, metadata)

        return view

    @staticmethod
    def _entity_key(partition_id: str, entity_id: str, prefix: bool) -> str:
        if not prefix:
            return str(entity_id)
        safe_partition = str(partition_id).replace(" ", "_")
        return f"{safe_partition}::{entity_id}"

    @staticmethod
    def _map_entity_type(kind: str) -> str:
        normalized = kind.strip().lower()
        return _KG_ENTITY_MAP.get(normalized, "system")

    @staticmethod
    def _map_relation(kind: str) -> str:
        normalized = kind.strip().lower()
        return _KG_RELATION_MAP.get(normalized, "related_to")
