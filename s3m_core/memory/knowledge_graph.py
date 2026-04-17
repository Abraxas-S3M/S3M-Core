"""Structured operational knowledge graph for S3M.

Military/tactical context:
The graph captures entities and relationships discovered during missions so
the planner can rapidly recover dependencies, prior solutions, and threat
causality without relying on external services.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re

import networkx as nx
from networkx.readwrite import json_graph

_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


class S3MKnowledgeGraph:
    """Structured knowledge store that grows as S3M operates."""

    ENTITY_TYPES = {
        "person",
        "organization",
        "system",
        "tool",
        "concept",
        "vulnerability",
        "document",
        "codebase",
        "service",
    }
    RELATIONSHIP_TYPES = {
        "uses",
        "depends_on",
        "related_to",
        "part_of",
        "discovered_by",
        "solved_with",
        "caused_by",
    }

    def __init__(self, storage_path: str = "./s3m_missions/knowledge_graph.json") -> None:
        path = str(storage_path).strip()
        if not path:
            raise ValueError("storage_path must be a non-empty string")
        target = Path(path)
        self.storage_path = target if target.suffix else target / "knowledge_graph.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.graph = nx.MultiDiGraph()
        self._load()

    def add_entity(self, entity_id: str, entity_type: str, attributes: dict[str, Any]) -> None:
        """Add or update an entity node."""

        normalized_id = self._validate_identifier(entity_id, field_name="entity_id")
        normalized_type = str(entity_type).strip().lower()
        if normalized_type not in self.ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of: {sorted(self.ENTITY_TYPES)}")
        if not isinstance(attributes, dict):
            raise ValueError("attributes must be a dictionary")

        self.graph.add_node(
            normalized_id,
            entity_type=normalized_type,
            attributes=self._sanitize_mapping(attributes),
        )
        self._save()

    def add_relationship(self, source: str, target: str, relationship_type: str, metadata: dict[str, Any]) -> None:
        """Add a typed relationship between existing entities."""

        source_id = self._validate_identifier(source, field_name="source")
        target_id = self._validate_identifier(target, field_name="target")
        relation = str(relationship_type).strip().lower()
        if relation not in self.RELATIONSHIP_TYPES:
            raise ValueError(f"relationship_type must be one of: {sorted(self.RELATIONSHIP_TYPES)}")
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a dictionary")
        if source_id not in self.graph or target_id not in self.graph:
            raise KeyError("source and target must exist before adding a relationship")

        self.graph.add_edge(
            source_id,
            target_id,
            key=relation,
            relationship_type=relation,
            metadata=self._sanitize_mapping(metadata),
        )
        self._save()

    def query(self, question: str) -> list[dict[str, Any]]:
        """Run a lightweight natural language query over the graph."""

        prompt = str(question).strip()
        if not prompt:
            raise ValueError("question must be non-empty")
        tokens = self._tokens(prompt)
        if not tokens:
            return []

        scored: list[dict[str, Any]] = []
        for node_id, node_data in self.graph.nodes(data=True):
            searchable = " ".join(
                [
                    str(node_id),
                    str(node_data.get("entity_type", "")),
                    json.dumps(node_data.get("attributes", {}), sort_keys=True),
                ]
            ).lower()
            score = self._score_tokens(tokens, searchable)
            if score > 0.0:
                scored.append(
                    {
                        "kind": "entity",
                        "entity_id": node_id,
                        "entity_type": node_data.get("entity_type", "unknown"),
                        "attributes": node_data.get("attributes", {}),
                        "score": score,
                    }
                )

        for source, target, edge_data in self.graph.edges(data=True):
            searchable = " ".join(
                [
                    str(source),
                    str(target),
                    str(edge_data.get("relationship_type", "")),
                    json.dumps(edge_data.get("metadata", {}), sort_keys=True),
                ]
            ).lower()
            score = self._score_tokens(tokens, searchable)
            if score > 0.0:
                scored.append(
                    {
                        "kind": "relationship",
                        "source": source,
                        "target": target,
                        "relationship_type": edge_data.get("relationship_type", "related_to"),
                        "metadata": edge_data.get("metadata", {}),
                        "score": score,
                    }
                )

        scored.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
        return scored[:20]

    def get_context_for_task(self, task: str) -> str:
        """Return a relevant knowledge subgraph as compact task context."""

        prompt = str(task).strip()
        if not prompt:
            raise ValueError("task must be non-empty")

        results = self.query(prompt)
        if not results:
            return "No relevant knowledge available for this task."

        top_results = results[:10]
        entity_ids: set[str] = set()
        context_lines = ["Relevant Operational Knowledge"]

        for item in top_results:
            if item["kind"] == "entity":
                entity_ids.add(str(item["entity_id"]))
                context_lines.append(
                    f"- Entity: {item['entity_id']} ({item['entity_type']}) attributes={item['attributes']}"
                )
            else:
                entity_ids.add(str(item["source"]))
                entity_ids.add(str(item["target"]))
                context_lines.append(
                    f"- Relationship: {item['source']} --{item['relationship_type']}--> {item['target']} metadata={item['metadata']}"
                )

        # Tactical context: connected edges expose dependency chains that can
        # impact mission sequencing and failure propagation.
        context_lines.append("Connected Subgraph Edges")
        edge_count = 0
        for source, target, edge_data in self.graph.edges(data=True):
            if source in entity_ids or target in entity_ids:
                context_lines.append(
                    f"- {source} --{edge_data.get('relationship_type', 'related_to')}--> {target}"
                )
                edge_count += 1
            if edge_count >= 20:
                break

        return "\n".join(context_lines)

    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
            graph = json_graph.node_link_graph(payload, directed=True, multigraph=True)
        except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError):
            return
        if isinstance(graph, nx.MultiDiGraph):
            self.graph = graph

    def _save(self) -> None:
        payload = json_graph.node_link_data(self.graph)
        self.storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _validate_identifier(value: str, *, field_name: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError(f"{field_name} must be non-empty")
        if len(cleaned) > 256:
            raise ValueError(f"{field_name} is too long")
        return cleaned

    @staticmethod
    def _sanitize_mapping(payload: dict[str, Any]) -> dict[str, Any]:
        serialized = json.dumps(payload, default=str)
        parsed = json.loads(serialized)
        if not isinstance(parsed, dict):
            return {}
        return parsed

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {match for match in _TOKEN_PATTERN.findall(text.lower()) if len(match) > 2}

    @staticmethod
    def _score_tokens(tokens: set[str], searchable: str) -> float:
        if not tokens:
            return 0.0
        matches = sum(1 for token in tokens if token in searchable)
        return matches / len(tokens)
