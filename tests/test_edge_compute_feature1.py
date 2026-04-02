"""
Unit tests for S3M Edge Compute - Feature 1: Edge CPU Network
Tests federated learning, self-training, self-replication, data generation,
knowledge graph, and sandbox controller.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

models = pytest.importorskip("src.edge_compute.models")

AggregationStrategy = models.AggregationStrategy
EdgeNodeInfo = models.EdgeNodeInfo
NodeStatus = models.NodeStatus
SelfTrainingStrategy = models.SelfTrainingStrategy


# ===========================================================
# Federated Engine Tests
# ===========================================================

class TestFederatedEngine:
    """Tests for federated learning aggregation, DP, and compression."""

    def _make_engine(self):
        from src.edge_compute.federated_engine import FederatedEngine
        return FederatedEngine(
            strategy=AggregationStrategy.FEDPROX,
            local_epochs=2,
            learning_rate=0.001,
            mu=0.01,
            min_nodes=2,
            dp_epsilon=8.0,
            compression_sparsity=0.9,
        )

    def _make_params(self, seed=42):
        rng = np.random.RandomState(seed)
        return {
            "W1": rng.randn(16, 32).astype(np.float32),
            "b1": rng.randn(32).astype(np.float32),
            "W2": rng.randn(32, 4).astype(np.float32),
            "b2": rng.randn(4).astype(np.float32),
        }

    def test_initialization(self):
        engine = self._make_engine()
        assert engine.strategy == AggregationStrategy.FEDPROX
        assert engine.min_nodes == 2

    def test_node_registration(self):
        engine = self._make_engine()
        node = EdgeNodeInfo(hostname="test-node", cpu_cores=4, memory_mb=4096)
        engine.register_node(node)
        assert len(engine.active_nodes()) == 1
        engine.deregister_node(node.node_id)
        assert len(engine.active_nodes()) == 0

    def test_global_model_init(self):
        engine = self._make_engine()
        params = self._make_params()
        engine.initialize_global_model(params)
        retrieved = engine.get_global_params()
        for name in params:
            np.testing.assert_array_equal(retrieved[name], params[name])

    def test_fedavg_round(self):
        from src.edge_compute.federated_engine import FederatedEngine
        engine = FederatedEngine(strategy=AggregationStrategy.FEDAVG, min_nodes=2)
        params = self._make_params()
        engine.initialize_global_model(params)

        # Simulate 2 nodes with slightly perturbed params
        updates = {
            "node_a": {k: v + np.random.randn(*v.shape).astype(np.float32) * 0.01 for k, v in params.items()},
            "node_b": {k: v + np.random.randn(*v.shape).astype(np.float32) * 0.01 for k, v in params.items()},
        }
        fed_round = engine.run_round(updates, {"node_a": 100, "node_b": 200})
        assert fed_round.round_id == 1
        assert len(fed_round.participating_nodes) == 2
        assert fed_round.duration_seconds > 0

    def test_fedprox_round(self):
        engine = self._make_engine()
        params = self._make_params()
        engine.initialize_global_model(params)

        updates = {
            f"node_{i}": {k: v + np.random.randn(*v.shape).astype(np.float32) * 0.01
                          for k, v in params.items()}
            for i in range(3)
        }
        fed_round = engine.run_round(updates)
        assert fed_round.round_id == 1
        assert fed_round.gradients_compressed is True
        assert fed_round.dp_applied is True

    def test_hierarchical_aggregation(self):
        from src.edge_compute.federated_engine import FederatedEngine
        engine = FederatedEngine(strategy=AggregationStrategy.HIERARCHICAL, min_nodes=2)
        params = self._make_params()
        engine.initialize_global_model(params)

        updates = {
            f"node_{i}": {k: v + np.random.randn(*v.shape).astype(np.float32) * 0.01
                          for k, v in params.items()}
            for i in range(6)
        }
        fed_round = engine.run_round(updates)
        assert fed_round.round_id == 1

    def test_scaffold_round(self):
        from src.edge_compute.federated_engine import FederatedEngine
        engine = FederatedEngine(strategy=AggregationStrategy.SCAFFOLD, min_nodes=2)
        params = self._make_params()
        engine.initialize_global_model(params)

        updates = {
            f"node_{i}": {k: v + np.random.randn(*v.shape).astype(np.float32) * 0.01
                          for k, v in params.items()}
            for i in range(2)
        }
        controls = {
            f"node_{i}": {k: np.zeros_like(v) for k, v in params.items()}
            for i in range(2)
        }
        fed_round = engine.run_round(updates, local_controls=controls)
        assert fed_round.round_id == 1

    def test_dp_budget_tracking(self):
        engine = self._make_engine()
        dp = engine.dp_status()
        assert dp["epsilon_budget"] == 8.0
        assert dp["epsilon_spent"] == 0.0
        assert dp["budget_exhausted"] is False

    def test_insufficient_nodes_skips_round(self):
        engine = self._make_engine()
        params = self._make_params()
        engine.initialize_global_model(params)
        # Only 1 node, but min is 2
        updates = {"solo_node": {k: v.copy() for k, v in params.items()}}
        fed_round = engine.run_round(updates)
        assert fed_round.round_id == 0  # Not incremented

    def test_health_check(self):
        engine = self._make_engine()
        health = engine.health_check()
        assert "strategy" in health
        assert "dp" in health
        assert "active_nodes" in health


class TestGradientCompression:
    """Tests for TopK compression and error feedback."""

    def test_topk_compress_basic(self):
        from src.edge_compute.federated_engine import topk_compress, decompress_gradient
        grad = np.random.randn(1000).astype(np.float32)
        values, indices, residual = topk_compress(grad, sparsity=0.9)

        assert len(values) == 100  # top 10%
        assert len(indices) == 100
        assert residual.shape == grad.shape

    def test_decompress_roundtrip(self):
        from src.edge_compute.federated_engine import topk_compress, decompress_gradient
        grad = np.random.randn(500).astype(np.float32)
        values, indices, residual = topk_compress(grad, sparsity=0.5)
        reconstructed = decompress_gradient(values, indices, 500)
        assert reconstructed.shape == (500,)
        # Reconstructed should be non-zero at top-k positions
        assert np.count_nonzero(reconstructed) == 250

    def test_error_feedback_accumulation(self):
        from src.edge_compute.federated_engine import topk_compress
        grad = np.ones(100, dtype=np.float32)
        _, _, residual1 = topk_compress(grad, sparsity=0.9)
        # Residual should contain the dropped values
        assert np.abs(residual1).sum() > 0

        # Second round with error feedback should boost some values
        grad2 = np.ones(100, dtype=np.float32) * 0.1
        _, _, residual2 = topk_compress(grad2, sparsity=0.9, error_feedback=residual1)
        assert residual2.shape == (100,)


class TestRDPAccountant:
    """Tests for Renyi Differential Privacy accountant."""

    def test_clip_gradients(self):
        from src.edge_compute.federated_engine import RDPAccountant
        acc = RDPAccountant(epsilon=8.0, max_grad_norm=1.0)
        big_grad = np.ones(100, dtype=np.float32) * 10.0
        clipped = acc.clip_gradients(big_grad)
        assert np.linalg.norm(clipped) <= 1.0 + 1e-6

    def test_noise_addition(self):
        from src.edge_compute.federated_engine import RDPAccountant
        acc = RDPAccountant(epsilon=8.0)
        grad = np.zeros(100, dtype=np.float32)
        noised = acc.add_noise(grad, noise_multiplier=1.0)
        assert not np.allclose(noised, 0.0)

    def test_budget_exhaustion(self):
        from src.edge_compute.federated_engine import RDPAccountant
        acc = RDPAccountant(epsilon=0.01, delta=1e-5)
        # A few steps should exhaust a tiny budget
        for _ in range(5):
            acc.step(noise_multiplier=1.0)
        assert acc.budget_exhausted is True


# ===========================================================
# Self-Training Tests
# ===========================================================

class TestSelfTraining:
    """Tests for Noisy Student, pseudo-labeling, and co-training."""

    def _make_data(self, n=100, d=16, c=4):
        x = np.random.randn(n, d).astype(np.float32)
        classes = np.random.randint(0, c, size=n)
        y = np.zeros((n, c), dtype=np.float32)
        y[np.arange(n), classes] = 1.0
        return x, y, c

    def test_numpy_model_forward(self):
        from src.edge_compute.self_training import NumpyLinearModel
        model = NumpyLinearModel(16, 32, 4)
        x = np.random.randn(10, 16).astype(np.float32)
        probs = model.forward(x)
        assert probs.shape == (10, 4)
        np.testing.assert_allclose(probs.sum(axis=-1), 1.0, atol=1e-5)

    def test_numpy_model_predict(self):
        from src.edge_compute.self_training import NumpyLinearModel
        model = NumpyLinearModel(16, 32, 4)
        x = np.random.randn(10, 16).astype(np.float32)
        classes, confidences = model.predict(x)
        assert classes.shape == (10,)
        assert confidences.shape == (10,)
        assert all(0.0 <= c <= 1.0 for c in confidences)

    def test_numpy_model_train_step(self):
        from src.edge_compute.self_training import NumpyLinearModel
        model = NumpyLinearModel(16, 32, 4)
        x, y, _ = self._make_data(50)
        grads = model.compute_gradients(x, y)
        assert set(grads.keys()) == {"W1", "b1", "W2", "b2"}
        loss = model.apply_gradients(grads, lr=0.01)
        assert loss > 0

    def test_numpy_model_clone(self):
        from src.edge_compute.self_training import NumpyLinearModel
        model = NumpyLinearModel(16, 32, 4)
        clone = model.clone()
        for k in model.params:
            np.testing.assert_array_equal(model.params[k], clone.params[k])
        # Mutating clone shouldn't affect original
        clone.params["b1"] += 1.0
        assert not np.array_equal(model.params["b1"], clone.params["b1"])

    def test_numpy_model_distill(self):
        from src.edge_compute.self_training import NumpyLinearModel
        model = NumpyLinearModel(16, 64, 4)
        student = model.distill_to(ratio=0.5)
        assert student.hidden_dim == 32

    def test_noisy_student_cycle(self):
        from src.edge_compute.self_training import SelfTrainingEngine, NumpyLinearModel
        engine = SelfTrainingEngine(
            strategy=SelfTrainingStrategy.NOISY_STUDENT,
            confidence_threshold=0.1,  # Low for test
        )
        model = NumpyLinearModel(16, 32, 4)
        engine.initialize(model)

        x, y, _ = self._make_data(50)
        unlabeled = np.random.randn(200, 16).astype(np.float32)

        batch = engine.train_cycle(x, y, unlabeled, epochs=2)
        assert batch.sample_count > 0
        assert batch.noise_applied is True

    def test_pseudo_label_cycle(self):
        from src.edge_compute.self_training import SelfTrainingEngine, NumpyLinearModel
        engine = SelfTrainingEngine(
            strategy=SelfTrainingStrategy.PSEUDO_LABEL,
            confidence_threshold=0.1,
        )
        model = NumpyLinearModel(16, 32, 4)
        engine.initialize(model)
        x, y, _ = self._make_data(50)
        unlabeled = np.random.randn(200, 16).astype(np.float32)
        batch = engine.train_cycle(x, y, unlabeled, epochs=2)
        assert batch.noise_applied is False

    def test_co_training_cycle(self):
        from src.edge_compute.self_training import SelfTrainingEngine, NumpyLinearModel
        engine = SelfTrainingEngine(
            strategy=SelfTrainingStrategy.CO_TRAINING,
            confidence_threshold=0.1,
        )
        model = NumpyLinearModel(16, 32, 4)
        engine.initialize(model)
        x, y, _ = self._make_data(50)
        unlabeled = np.random.randn(200, 16).astype(np.float32)
        batch = engine.train_cycle(x, y, unlabeled, epochs=2)
        assert batch.strategy == SelfTrainingStrategy.CO_TRAINING

    def test_health_check(self):
        from src.edge_compute.self_training import SelfTrainingEngine
        engine = SelfTrainingEngine()
        health = engine.health_check()
        assert "strategy" in health
        assert "cycle" in health


class TestNoiseAugmentations:
    """Tests for dropout, Gaussian, and mixup noise functions."""

    def test_dropout_noise(self):
        from src.edge_compute.self_training import dropout_noise
        x = np.ones((10, 16), dtype=np.float32)
        noised = dropout_noise(x, rate=0.5)
        assert noised.shape == x.shape
        assert not np.allclose(noised, x)

    def test_gaussian_noise(self):
        from src.edge_compute.self_training import gaussian_noise
        x = np.zeros((10, 16), dtype=np.float32)
        noised = gaussian_noise(x, std=0.1)
        assert not np.allclose(noised, 0.0)

    def test_mixup(self):
        from src.edge_compute.self_training import mixup
        x1 = np.ones((16,), dtype=np.float32)
        x2 = np.zeros((16,), dtype=np.float32)
        mixed, lam = mixup(x1, x2, alpha=0.2)
        assert mixed.shape == (16,)
        assert 0.0 <= lam <= 1.0


# ===========================================================
# Self-Replication Tests
# ===========================================================

class TestSelfReplication:
    """Tests for self-replication and model distillation."""

    def test_distillation_ratio_computation(self):
        from src.edge_compute.self_replication import ReplicationEngine
        ratio = ReplicationEngine.compute_distillation_ratio(
            target_memory_mb=4096,
            parent_model_size_mb=2048.0,
        )
        assert 0.2 <= ratio <= 1.0

    def test_distillation_ratio_small_device(self):
        from src.edge_compute.self_replication import ReplicationEngine
        ratio = ReplicationEngine.compute_distillation_ratio(
            target_memory_mb=512,
            parent_model_size_mb=4096.0,
        )
        assert ratio == 0.2  # Clamped to min

    def test_model_export_and_load(self):
        from src.edge_compute.self_replication import ReplicationEngine
        params = {"W1": np.random.randn(16, 32).astype(np.float32)}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = ReplicationEngine.export_model_snapshot(params, tmpdir, "test")
            assert os.path.exists(path)
            loaded = ReplicationEngine.load_model_snapshot(path)
            np.testing.assert_array_equal(loaded["W1"], params["W1"])

    def test_replica_creation_without_runtime(self):
        from src.edge_compute.self_replication import ReplicationEngine
        engine = ReplicationEngine(container_runtime="nonexistent_runtime", max_replicas=4)
        params = {"W1": np.random.randn(16, 32).astype(np.float32)}
        replica = engine.create_replica("parent-123", params, target_memory_mb=2048)
        assert replica.parent_node_id == "parent-123"
        assert replica.status == NodeStatus.OFFLINE  # No runtime
        assert 0.0 < replica.distillation_ratio <= 1.0

    def test_max_replicas_enforced(self):
        from src.edge_compute.self_replication import ReplicationEngine
        engine = ReplicationEngine(container_runtime="nonexistent", max_replicas=2)
        params = {"W1": np.random.randn(4, 4).astype(np.float32)}
        engine.create_replica("p1", params)
        engine.create_replica("p2", params)
        with pytest.raises(RuntimeError, match="Max replicas"):
            engine.create_replica("p3", params)

    def test_health_check(self):
        from src.edge_compute.self_replication import ReplicationEngine
        engine = ReplicationEngine(container_runtime="nonexistent")
        health = engine.health_check()
        assert health["max_replicas"] == 8
        assert health["runtime_available"] is False


# ===========================================================
# Data Generation Tests
# ===========================================================

class TestDataGeneration:
    """Tests for contrastive augmentation, generative replay, active learning, and KG."""

    def test_contrastive_pairs(self):
        from src.edge_compute.data_generation import ContrastiveAugmentor
        aug = ContrastiveAugmentor()
        data = np.random.randn(100, 16).astype(np.float32)
        pairs = aug.generate_pairs(data, n_pairs=50)
        assert pairs["anchors"].shape == (50, 16)
        assert pairs["positives"].shape == (50, 16)
        assert pairs["negatives"].shape == (50, 16)

    def test_contrastive_loss(self):
        from src.edge_compute.data_generation import ContrastiveAugmentor
        aug = ContrastiveAugmentor()
        a = np.random.randn(50, 16).astype(np.float32)
        p = a + np.random.randn(50, 16).astype(np.float32) * 0.01
        n = np.random.randn(50, 16).astype(np.float32)
        loss = aug.contrastive_loss(a, p, n)
        assert loss >= 0.0

    def test_generative_replay_fit_and_replay(self):
        from src.edge_compute.data_generation import GenerativeReplay
        replay = GenerativeReplay(n_components=3)
        features = np.random.randn(100, 8).astype(np.float32)
        replay.fit_class(0, features)
        samples = replay.replay(0, 50)
        assert samples.shape == (50, 8)

    def test_generative_replay_all_classes(self):
        from src.edge_compute.data_generation import GenerativeReplay
        replay = GenerativeReplay()
        for c in range(3):
            replay.fit_class(c, np.random.randn(50, 8).astype(np.float32) + c)
        features, labels = replay.replay_all(n_per_class=20)
        assert features.shape == (60, 8)
        assert len(labels) == 60

    def test_active_learner_uncertainty(self):
        from src.edge_compute.data_generation import ActiveLearner
        learner = ActiveLearner(strategy="uncertainty")
        probs = np.random.dirichlet(np.ones(4), size=100).astype(np.float32)
        unlabeled = np.random.randn(100, 16).astype(np.float32)
        selected = learner.select(unlabeled, probs, batch_size=20)
        assert len(selected) == 20

    def test_active_learner_diversity(self):
        from src.edge_compute.data_generation import ActiveLearner
        learner = ActiveLearner(strategy="diversity")
        probs = np.random.dirichlet(np.ones(4), size=100).astype(np.float32)
        unlabeled = np.random.randn(100, 16).astype(np.float32)
        selected = learner.select(unlabeled, probs, batch_size=10)
        assert len(selected) == 10

    def test_knowledge_graph_add_and_query(self):
        from src.edge_compute.data_generation import KnowledgeGraphBuilder
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_kg.db")
            kg = KnowledgeGraphBuilder(db_path=db_path)
            try:
                eid1 = kg.add_entity("Alpha", "unit")
                eid2 = kg.add_entity("Bravo", "unit")
                kg.add_edge(eid1, eid2, "supports", confidence=0.9)
                neighbors = kg.query_neighbors("Alpha")
                assert len(neighbors) == 1
                assert neighbors[0]["name"] == "Bravo"
                stats = kg.stats()
                assert stats["entities"] == 2
                assert stats["edges"] == 1
            finally:
                kg.close()

    def test_pmi_edge_discovery(self):
        from src.edge_compute.data_generation import KnowledgeGraphBuilder
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "pmi_test.db")
            kg = KnowledgeGraphBuilder(db_path=db_path)
            try:
                kg.add_entity("Tank", "vehicle")
                kg.add_entity("RPG", "weapon")
                for _ in range(5):
                    kg.record_co_occurrence("Tank", "RPG")
                new_edges = kg.compute_pmi_edges(min_count=3, min_pmi=0.1)
                assert new_edges >= 1
            finally:
                kg.close()

    def test_data_gen_engine_contrastive(self):
        from src.edge_compute.data_generation import DataGenerationEngine
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = DataGenerationEngine(
                output_dir=os.path.join(tmpdir, "gen"),
                kg_db_path=os.path.join(tmpdir, "kg.db"),
            )
            data = np.random.randn(200, 16).astype(np.float32)
            ds = engine.generate_contrastive_dataset(data, n_pairs=100)
            assert ds.record_count == 100
            assert os.path.exists(ds.file_path)
            engine.knowledge_graph.close()


# ===========================================================
# Sandbox Controller Tests
# ===========================================================

class TestSandboxController:
    """Tests for sandbox deployment and parameter toggling."""

    def test_deploy_without_runtime(self):
        from src.edge_compute.sandbox_controller import SandboxController
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = SandboxController(
                runtime="nonexistent_runtime",
                work_dir=os.path.join(tmpdir, "sandboxes"),
            )
            state = ctrl.deploy(cpu_cores=2, memory_mb=1024)
            assert state.sandbox_id
            assert state.running is False  # No runtime
            assert state.parameters.get("training_enabled") is True

    def test_param_update(self):
        from src.edge_compute.sandbox_controller import SandboxController
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = SandboxController(
                runtime="nonexistent_runtime",
                work_dir=os.path.join(tmpdir, "sandboxes"),
            )
            state = ctrl.deploy()
            updated = ctrl.update_params(state.sandbox_id, {"temperature": 0.3})
            assert updated["temperature"] == 0.3

            # Read back
            params = ctrl.get_params(state.sandbox_id)
            assert params["temperature"] == 0.3

    def test_param_file_persisted(self):
        from src.edge_compute.sandbox_controller import SandboxController
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = SandboxController(runtime="nonexistent", work_dir=os.path.join(tmpdir, "sb"))
            state = ctrl.deploy(params={"custom_key": "custom_value"})
            param_path = ctrl._param_file(state.sandbox_id)
            assert os.path.exists(param_path)
            with open(param_path) as f:
                data = json.load(f)
            assert data["custom_key"] == "custom_value"

    def test_stop_sandbox(self):
        from src.edge_compute.sandbox_controller import SandboxController
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = SandboxController(runtime="nonexistent", work_dir=os.path.join(tmpdir, "sb"))
            state = ctrl.deploy()
            ok = ctrl.stop(state.sandbox_id)
            assert ok is True

    def test_list_sandboxes(self):
        from src.edge_compute.sandbox_controller import SandboxController
        with tempfile.TemporaryDirectory() as tmpdir:
            ctrl = SandboxController(runtime="nonexistent", work_dir=os.path.join(tmpdir, "sb"))
            ctrl.deploy()
            ctrl.deploy()
            assert len(ctrl.list_sandboxes()) == 2

    def test_health_check(self):
        from src.edge_compute.sandbox_controller import SandboxController
        ctrl = SandboxController(runtime="nonexistent")
        health = ctrl.health_check()
        assert health["runtime_available"] is False
        assert health["total_sandboxes"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
