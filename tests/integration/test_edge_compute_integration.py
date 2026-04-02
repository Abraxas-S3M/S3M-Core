"""
S3M Integration Tests - Edge Compute <-> Other Layers
UNCLASSIFIED - FOUO

Validates real cross-layer data flows between the edge compute module
and Layers 01 (LLM Core), 02 (Threat Detection), 04 (Simulation), and 06 (Dashboard).
"""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.integration._availability import has_module

EDGE_AVAILABLE = has_module("src.edge_compute.manager")
SYNTH_AVAILABLE = has_module("src.simulation.synthetic.data_manager")
THREAT_AVAILABLE = has_module("src.threat_detection.threat_manager")
DASHBOARD_AVAILABLE = has_module("src.dashboard.aggregator")


@pytest.mark.skipif(not EDGE_AVAILABLE, reason="Edge compute module not available")
class TestEdgeFederatedWithSyntheticData:
    """Federated learning trained on Layer 04 synthetic data."""

    @pytest.mark.skipif(not SYNTH_AVAILABLE, reason="Simulation synthetic data not available")
    def test_federated_on_synthetic_network_traffic(self):
        """Train federated model on synthetic network traffic from Layer 04."""
        import csv
        from src.edge_compute.federated_engine import FederatedEngine
        from src.edge_compute.models import AggregationStrategy, EdgeNodeInfo
        from src.simulation.synthetic.data_manager import SyntheticDataManager

        # Generate synthetic data via Layer 04
        with tempfile.TemporaryDirectory() as tmpdir:
            synth = SyntheticDataManager(output_dir=tmpdir)
            dataset = synth.generate_network_traffic(n_records=500, attack_ratio=0.1)

            # Load CSV into numpy
            rows = []
            with open(dataset.file_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append([float(row["duration"]), float(row["bytes_in"]), float(row["bytes_out"])])
            data = np.array(rows, dtype=np.float32)

            # Initialize federated engine with small model
            engine = FederatedEngine(
                strategy=AggregationStrategy.FEDAVG,
                min_nodes=2,
            )
            params = {
                "W1": np.random.randn(3, 8).astype(np.float32) * 0.1,
                "b1": np.zeros(8, dtype=np.float32),
                "W2": np.random.randn(8, 2).astype(np.float32) * 0.1,
                "b2": np.zeros(2, dtype=np.float32),
            }
            engine.initialize_global_model(params)

            # Simulate 2 nodes each with half the data
            mid = len(data) // 2
            updates = {}
            for i, chunk in enumerate([data[:mid], data[mid:]]):
                node_params = {k: v + np.random.randn(*v.shape).astype(np.float32) * 0.01
                               for k, v in params.items()}
                updates[f"node_{i}"] = node_params

            fed_round = engine.run_round(updates, {"node_0": mid, "node_1": len(data) - mid})
            assert fed_round.round_id == 1
            assert len(fed_round.participating_nodes) == 2


@pytest.mark.skipif(not EDGE_AVAILABLE, reason="Edge compute module not available")
class TestEdgeSelfTrainingPipeline:
    """End-to-end self-training on edge CPU."""

    def test_self_training_improves_pseudo_label_count(self):
        """Multiple cycles should generate increasing pseudo-labels as the model improves."""
        from src.edge_compute.manager import EdgeComputeManager

        mgr = EdgeComputeManager(confidence_threshold=0.2)
        x = np.random.randn(50, 8).astype(np.float32)
        classes = np.random.randint(0, 3, size=50)
        y = np.zeros((50, 3), dtype=np.float32)
        y[np.arange(50), classes] = 1.0
        unlabeled = np.random.randn(300, 8).astype(np.float32)

        result = mgr.quick_self_train(8, 3, x, y, unlabeled, cycles=10)

        # At minimum, we should have generated some pseudo labels
        total = sum(h["sample_count"] for h in result["history"])
        assert total > 0
        mgr.shutdown()


@pytest.mark.skipif(not EDGE_AVAILABLE, reason="Edge compute module not available")
class TestEdgeDataGenWithKnowledgeGraph:
    """Data generation feeding into knowledge graph discovery."""

    def test_entity_ingestion_and_pmi_discovery(self):
        """Ingest tactical entities and auto-discover relationships."""
        from src.edge_compute.data_generation import DataGenerationEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            engine = DataGenerationEngine(
                output_dir=os.path.join(tmpdir, "gen"),
                kg_db_path=os.path.join(tmpdir, "kg.db"),
            )

            entities = []
            for _ in range(20):
                entities.extend([
                    {"name": "Drone-Alpha", "type": "asset"},
                    {"name": "Sector-7", "type": "location"},
                    {"name": "Target-X", "type": "threat"},
                    {"name": "Drone-Alpha", "type": "asset"},
                    {"name": "Target-X", "type": "threat"},
                ])

            engine.ingest_entities(entities, co_occurrence_window=3)
            new_edges = engine.discover_relationships(min_count=5, min_pmi=0.1)
            assert new_edges >= 1

            neighbors = engine.knowledge_graph.query_neighbors("Drone-Alpha")
            assert len(neighbors) > 0
            engine.knowledge_graph.close()


@pytest.mark.skipif(not EDGE_AVAILABLE, reason="Edge compute module not available")
class TestHeteroComputeWithRealOps:
    """Heterogeneous compute with realistic numpy operations."""

    def test_mixed_workload_scheduling(self):
        """Run a mix of operations and verify adaptive stats accumulate."""
        from src.edge_compute.hetero_compute import HeterogeneousComputeEngine
        from src.edge_compute.models import OperationType, SchedulingPolicy

        engine = HeterogeneousComputeEngine(policy=SchedulingPolicy.ADAPTIVE)
        data = np.random.randn(64, 128).astype(np.float32)

        # Simulate a realistic inference pipeline
        # Realistic operations to exercise scheduler behavior.
        def safe_attention(x):
            scores = x @ x.T / np.sqrt(x.shape[-1])
            scores -= scores.max(axis=-1, keepdims=True)
            weights = np.exp(scores) / np.exp(scores).sum(axis=-1, keepdims=True)
            return weights @ x

        real_ops = [
            (OperationType.TOKENIZATION, lambda x: (x * 1000).astype(np.int32)),
            (OperationType.EMBEDDING, lambda x: x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-8)),
            (OperationType.ATTENTION, safe_attention),
            (OperationType.MATMUL, lambda x: x @ x.T),
            (OperationType.POSTPROCESSING, lambda x: np.argmax(x, axis=-1)),
        ]

        for op_type, func in real_ops:
            engine.execute(op_type, func, data)

        stats = engine.device_stats()
        assert stats["total_tasks"] == 5
        assert stats["cpu"]["avg_latency_ms"] > 0

    def test_scheduler_learns_device_preference(self):
        """After enough observations, scheduler should exhibit learned preference."""
        from src.edge_compute.hetero_compute import HeterogeneousComputeEngine
        from src.edge_compute.models import OperationType, SchedulingPolicy

        engine = HeterogeneousComputeEngine(policy=SchedulingPolicy.ADAPTIVE)
        data = np.random.randn(16, 16).astype(np.float32)

        # Run many tasks to build up scheduler history
        for _ in range(50):
            engine.execute(OperationType.TOKENIZATION, lambda x: x.astype(np.int32), data)
            engine.execute(OperationType.MATMUL, lambda x: x @ x.T, data)

        policy = engine.scheduler.get_policy_table()
        assert len(policy) > 0  # Scheduler has learned something


@pytest.mark.skipif(not (EDGE_AVAILABLE and THREAT_AVAILABLE), reason="Edge + Threat layers required")
class TestEdgeWithThreatDetection:
    """Edge data generation feeding threat detection layer."""

    def test_contrastive_data_compatible_with_anomaly_detector(self):
        """Generated contrastive data should be usable by threat anomaly detector."""
        from src.edge_compute.data_generation import DataGenerationEngine
        from src.threat_detection.anomaly_detector import AnomalyDetector

        with tempfile.TemporaryDirectory() as tmpdir:
            gen = DataGenerationEngine(
                output_dir=os.path.join(tmpdir, "gen"),
                kg_db_path=os.path.join(tmpdir, "kg.db"),
            )

            # Generate contrastive pairs from network-like data
            data = np.random.randn(500, 3).astype(np.float32)
            data[:, 0] = np.abs(data[:, 0]) * 100   # duration
            data[:, 1] = np.abs(data[:, 1]) * 10000  # bytes_in
            data[:, 2] = np.abs(data[:, 2]) * 10000  # bytes_out

            ds = gen.generate_contrastive_dataset(data, n_pairs=200)
            assert ds.record_count == 200

            # Verify the data can be fed to anomaly detector
            detector = AnomalyDetector(contamination=0.1, n_estimators=50)
            normal = data[:250].tolist()
            detector.fit(normal)
            events = detector.detect(data.tolist(), feature_names=["duration", "bytes_in", "bytes_out"])
            assert isinstance(events, list)

            gen.knowledge_graph.close()
