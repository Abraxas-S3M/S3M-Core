#!/usr/bin/env python3
"""Unit tests for edge autonomous data generation engine."""

from __future__ import annotations

import numpy as np

from src.edge_compute.data_generation import (
    ActiveLearner,
    ContrastiveAugmentor,
    DataGenerationEngine,
    GenerativeReplay,
    KnowledgeGraphBuilder,
)
from src.edge_compute.models import DataGenStrategy


def test_contrastive_augmentor_generates_triplets_and_loss():
    np.random.seed(7)
    data = np.random.randn(50, 8).astype(np.float32)
    augmentor = ContrastiveAugmentor(positive_radius=0.02, negative_radius=0.2)
    pairs = augmentor.generate_pairs(data, n_pairs=100)

    assert set(pairs.keys()) == {"anchors", "positives", "negatives"}
    assert pairs["anchors"].shape == (100, 8)
    assert pairs["positives"].shape == (100, 8)
    assert pairs["negatives"].shape == (100, 8)

    loss = augmentor.contrastive_loss(pairs["anchors"], pairs["positives"], pairs["negatives"])
    assert isinstance(loss, float)
    assert loss >= 0.0


def test_generative_replay_fit_and_replay_all():
    np.random.seed(11)
    replay = GenerativeReplay(n_components=3)
    class0 = np.random.normal(loc=0.0, scale=1.0, size=(40, 6)).astype(np.float32)
    class1 = np.random.normal(loc=2.0, scale=1.2, size=(35, 6)).astype(np.float32)

    replay.fit_class(0, class0)
    replay.fit_class(1, class1)
    x_syn, y_syn = replay.replay_all(n_per_class=25)

    assert x_syn.shape == (50, 6)
    assert y_syn.shape == (50,)
    assert set(np.unique(y_syn).tolist()) == {0, 1}


def test_active_learner_expected_model_change_prefers_large_gradients():
    np.random.seed(3)
    n = 20
    unlabeled = np.random.randn(n, 4).astype(np.float32)
    probs = np.tile(np.array([[0.5, 0.5]], dtype=np.float32), (n, 1))
    gradients = np.zeros((n, 4), dtype=np.float32)
    gradients[-1] = np.array([9.0, 0.0, 0.0, 0.0], dtype=np.float32)
    gradients[-2] = np.array([8.0, 0.0, 0.0, 0.0], dtype=np.float32)

    learner = ActiveLearner(strategy="expected_model_change")
    selected = learner.select(unlabeled, probs, batch_size=2, model_gradients=gradients)

    assert selected.shape == (2,)
    assert set(selected.tolist()) == {n - 2, n - 1}


def test_knowledge_graph_builder_pmi_discovery_and_query(tmp_path):
    db_path = tmp_path / "kg.sqlite3"
    kg = KnowledgeGraphBuilder(db_path=str(db_path))
    try:
        for name in ["UAV-ALPHA", "RADAR-SITE-1", "SECTOR-RED"]:
            kg.add_entity(name=name, entity_type="asset")

        # Tactical context: repeated pair co-occurrence should form a strong PMI link.
        for _ in range(5):
            kg.record_co_occurrence("UAV-ALPHA", "RADAR-SITE-1")
        for _ in range(2):
            kg.record_co_occurrence("UAV-ALPHA", "SECTOR-RED")

        new_edges = kg.compute_pmi_edges(min_count=3, min_pmi=0.0)
        assert new_edges >= 1

        neighbors = kg.query_neighbors("UAV-ALPHA", max_hops=2)
        assert any(item["name"] == "RADAR-SITE-1" for item in neighbors)
        stats = kg.stats()
        assert stats["entities"] == 3
        assert stats["edges"] >= 1
    finally:
        kg.close()


def test_data_generation_engine_outputs_artifacts_and_health(tmp_path):
    np.random.seed(21)
    output_dir = tmp_path / "generated"
    kg_db = tmp_path / "knowledge.db"
    engine = DataGenerationEngine(output_dir=str(output_dir), kg_db_path=str(kg_db))
    try:
        base = np.random.randn(60, 10).astype(np.float32)
        contrastive_ds = engine.generate_contrastive_dataset(base, n_pairs=120)
        assert contrastive_ds.strategy == DataGenStrategy.CONTRASTIVE
        assert contrastive_ds.record_count == 120
        assert contrastive_ds.file_size_bytes > 0

        class_features = {
            0: np.random.randn(40, 10).astype(np.float32),
            1: np.random.randn(35, 10).astype(np.float32),
        }
        replay_ds = engine.generate_replay_dataset(class_features, n_per_class=30)
        assert replay_ds.strategy == DataGenStrategy.GENERATIVE_REPLAY
        assert replay_ds.record_count == 60
        assert replay_ds.file_size_bytes > 0

        records = [
            {"name": "UNIT-A", "type": "friendly", "context": "patrol"},
            {"name": "ZONE-X", "type": "location", "context": "patrol"},
            {"name": "UNIT-A", "type": "friendly", "context": "patrol"},
            {"name": "RADAR-1", "type": "sensor", "context": "contact"},
            {"name": "ZONE-X", "type": "location", "context": "contact"},
        ]
        added = engine.ingest_entities(records, co_occurrence_window=3)
        assert added >= 3
        discovered = engine.discover_relationships(min_count=1, min_pmi=-1.0)
        assert discovered >= 1

        health = engine.health_check()
        assert health["datasets_generated"] == 2
        assert health["replay_classes_fitted"] == 2
        assert health["knowledge_graph"]["entities"] >= 3
        assert health["knowledge_graph"]["edges"] >= 1
        assert len(engine.list_generated()) == 2
    finally:
        engine.close()
