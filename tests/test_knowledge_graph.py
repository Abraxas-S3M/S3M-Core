"""Unit tests for S3M operational knowledge graph."""

from __future__ import annotations

from s3m_core.memory.knowledge_graph import S3MKnowledgeGraph


def test_knowledge_graph_add_query_and_context(tmp_path) -> None:
    graph_path = tmp_path / "knowledge_graph.json"
    graph = S3MKnowledgeGraph(storage_path=str(graph_path))

    graph.add_entity("sensor_fusion_core", "system", {"domain": "targeting", "status": "active"})
    graph.add_entity("ew_risk_model", "tool", {"purpose": "spectrum-threat estimation"})
    graph.add_relationship(
        "sensor_fusion_core",
        "ew_risk_model",
        "uses",
        {"reason": "predict jamming windows"},
    )

    results = graph.query("Which system uses EW risk model for jamming windows?")
    assert results
    assert any(item.get("kind") == "relationship" for item in results)

    context = graph.get_context_for_task("Plan route while accounting for EW risk model dependencies")
    assert "sensor_fusion_core --uses--> ew_risk_model" in context


def test_knowledge_graph_persists_across_instances(tmp_path) -> None:
    graph_path = tmp_path / "knowledge_graph.json"
    graph = S3MKnowledgeGraph(storage_path=str(graph_path))
    graph.add_entity("mission_brief", "document", {"owner": "ops"})

    reloaded = S3MKnowledgeGraph(storage_path=str(graph_path))
    results = reloaded.query("mission brief document")
    assert any(item.get("entity_id") == "mission_brief" for item in results if item.get("kind") == "entity")
