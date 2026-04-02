"""
Unit tests for S3M Edge Compute Expansion:
  - Self-Growth Engine (NAS-inspired dynamic layer expansion)
  - Governed Replication (security-hardened with crypto auth)
  - Data Value Assessor (MoD mission tagging + self-cleaning)
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════
# Self-Growth Engine Tests
# ═══════════════════════════════════════════════════════════


class TestPlateauDetector:
    def test_no_plateau_when_improving(self):
        from src.edge_compute.self_growth import PlateauDetector

        det = PlateauDetector(patience=3, min_delta=0.01)
        # Steadily decreasing loss
        for loss in [1.0, 0.9, 0.8, 0.7, 0.6]:
            assert det.record(loss) is False

    def test_plateau_detected_when_stalled(self):
        from src.edge_compute.self_growth import PlateauDetector

        det = PlateauDetector(patience=3, min_delta=0.01)
        det.record(1.0)
        det.record(0.5)  # Big improvement
        # Now stall
        assert det.record(0.500) is False  # stall 1
        assert det.record(0.499) is False  # stall 2
        assert det.record(0.498) is True  # stall 3 → plateau

    def test_reset(self):
        from src.edge_compute.self_growth import PlateauDetector

        det = PlateauDetector(patience=2)
        det.record(1.0)
        det.record(1.0)
        det.reset()
        assert det._stall_count == 0
        assert det._best_value is None


class TestGrowableModel:
    def test_init(self):
        from src.edge_compute.self_growth import GrowableModel

        model = GrowableModel(16, 32, 4, n_hidden_layers=2)
        assert model.n_layers == 3  # 2 hidden + 1 output

    def test_forward_shape(self):
        from src.edge_compute.self_growth import GrowableModel

        model = GrowableModel(16, 32, 4, n_hidden_layers=2)
        x = np.random.randn(10, 16).astype(np.float32)
        probs = model.forward(x)
        assert probs.shape == (10, 4)
        np.testing.assert_allclose(probs.sum(axis=-1), 1.0, atol=1e-5)

    def test_grow_adds_layers(self):
        from src.edge_compute.self_growth import GrowableModel

        model = GrowableModel(16, 32, 4, n_hidden_layers=2)
        before = model.n_layers
        event = model.grow(n_new_layers=3)
        assert model.n_layers == before + 3
        assert event["layers_added"] == 3

    def test_grow_preserves_output(self):
        from src.edge_compute.self_growth import GrowableModel

        model = GrowableModel(16, 32, 4, n_hidden_layers=2)
        x = np.random.randn(5, 16).astype(np.float32)
        out_before = model.forward(x)
        model.grow(n_new_layers=1, perturbation_scale=0.0001)
        out_after = model.forward(x)
        # With tiny perturbation, outputs should be very close
        np.testing.assert_allclose(out_before, out_after, atol=0.1)

    def test_topology(self):
        from src.edge_compute.self_growth import GrowableModel

        model = GrowableModel(16, 32, 4, n_hidden_layers=3)
        topo = model.topology()
        assert len(topo) == 4  # 3 hidden + 1 output
        assert topo[-1]["type"] == "output"
        assert all(t["type"] == "hidden" for t in topo[:-1])

    def test_memory_increases_with_growth(self):
        from src.edge_compute.self_growth import GrowableModel

        model = GrowableModel(16, 64, 4, n_hidden_layers=2)
        mem_before = model.memory_mb
        model.grow(5)
        assert model.memory_mb > mem_before

    def test_widen(self):
        from src.edge_compute.self_growth import GrowableModel

        model = GrowableModel(16, 32, 4, n_hidden_layers=2)
        event = model.widen(64)
        assert model.hidden_dim == 64
        assert event["new_hidden_dim"] == 64


class TestSelfGrowthEngine:
    def _make_data(self, n: int = 100, d: int = 16, c: int = 4):
        x = np.random.randn(n, d).astype(np.float32)
        classes = np.random.randint(0, c, size=n)
        y = np.zeros((n, c), dtype=np.float32)
        y[np.arange(n), classes] = 1.0
        return x, y

    def test_initialization(self):
        from src.edge_compute.self_growth import SelfGrowthEngine

        engine = SelfGrowthEngine()
        engine.initialize(16, 32, 4, 2)
        assert engine.model is not None
        assert engine.model.n_layers == 3

    def test_train_cycle(self):
        from src.edge_compute.self_growth import SelfGrowthEngine

        engine = SelfGrowthEngine(patience=3, max_layers=20)
        engine.initialize(16, 32, 4, 2)
        tx, ty = self._make_data(80)
        vx, vy = self._make_data(20)
        result = engine.train_cycle(tx, ty, vx, vy, epochs=1)
        assert "train_loss" in result
        assert "val_loss" in result
        assert "layers" in result

    def test_forced_growth(self):
        from src.edge_compute.self_growth import SelfGrowthEngine

        engine = SelfGrowthEngine(max_layers=100)
        engine.initialize(16, 32, 4, 2)
        before = engine.model.n_layers
        event = engine.force_grow(3)
        assert event is not None
        assert engine.model.n_layers == before + 3

    def test_max_layers_respected(self):
        from src.edge_compute.self_growth import SelfGrowthEngine

        engine = SelfGrowthEngine(max_layers=4)
        engine.initialize(16, 32, 4, n_hidden_layers=2)
        # Model has 3 layers, max is 4, so can grow 1 more
        event = engine.force_grow(1)
        assert event is not None
        # Now at 4, cannot grow
        event2 = engine.force_grow(1)
        assert event2 is None

    def test_audit_callback(self):
        from src.edge_compute.self_growth import SelfGrowthEngine

        events = []
        engine = SelfGrowthEngine(max_layers=100)
        engine.set_audit_callback(lambda **kwargs: events.append(kwargs))
        engine.initialize(16, 32, 4, 2)
        engine.force_grow(1)
        assert len(events) == 1
        assert events[0]["action"] == "model_growth"

    def test_health_check(self):
        from src.edge_compute.self_growth import SelfGrowthEngine

        engine = SelfGrowthEngine()
        engine.initialize(16, 32, 4, 2)
        health = engine.health_check()
        assert "layers" in health
        assert "growth_events" in health
        assert "plateau_detector" in health


# ═══════════════════════════════════════════════════════════
# Governed Replication Tests
# ═══════════════════════════════════════════════════════════


class TestReplicationToken:
    def test_sign_and_verify(self):
        from src.edge_compute.governed_replication import ReplicationToken

        token = ReplicationToken("admin", "node-1", max_replicas=3, ttl_seconds=3600)
        token.sign("test-secret")
        assert token.signature != ""
        assert ReplicationToken.verify(token.to_dict(), "test-secret") is True

    def test_verify_fails_wrong_key(self):
        from src.edge_compute.governed_replication import ReplicationToken

        token = ReplicationToken("admin", "node-1")
        token.sign("correct-key")
        assert ReplicationToken.verify(token.to_dict(), "wrong-key") is False

    def test_verify_fails_expired(self):
        from src.edge_compute.governed_replication import ReplicationToken

        token = ReplicationToken("admin", "node-1", ttl_seconds=0)
        token.sign("key")
        time.sleep(0.1)
        assert ReplicationToken.verify(token.to_dict(), "key") is False

    def test_verify_fails_tampered(self):
        from src.edge_compute.governed_replication import ReplicationToken

        token = ReplicationToken("admin", "node-1", max_replicas=1)
        token.sign("key")
        tampered = token.to_dict()
        tampered["max_replicas"] = 999
        assert ReplicationToken.verify(tampered, "key") is False


class TestReplicationPolicy:
    def test_fleet_size_limit(self):
        from src.edge_compute.governed_replication import ReplicationPolicy

        policy = ReplicationPolicy()
        policy.set_max_fleet(3)
        violations = policy.evaluate(current_fleet_size=3)
        assert any(v["rule"] == "fleet_size_limit" for v in violations)

    def test_classification_gate(self):
        from src.edge_compute.governed_replication import ReplicationPolicy

        policy = ReplicationPolicy()
        policy.set_min_classification("SECRET")
        violations = policy.evaluate(current_fleet_size=0, target_classification="CONFIDENTIAL")
        assert any(v["rule"] == "classification_gate" for v in violations)

    def test_classification_passes(self):
        from src.edge_compute.governed_replication import ReplicationPolicy

        policy = ReplicationPolicy()
        policy.set_min_classification("CONFIDENTIAL")
        violations = policy.evaluate(current_fleet_size=0, target_classification="SECRET")
        assert not any(v["rule"] == "classification_gate" for v in violations)

    def test_subnet_restriction(self):
        from src.edge_compute.governed_replication import ReplicationPolicy

        policy = ReplicationPolicy()
        policy.set_allowed_subnets(["192.168.1.", "10.0.0."])
        violations = policy.evaluate(current_fleet_size=0, target_ip="172.16.0.5")
        assert any(v["rule"] == "subnet_restriction" for v in violations)

    def test_all_pass(self):
        from src.edge_compute.governed_replication import ReplicationPolicy

        policy = ReplicationPolicy()
        policy.set_max_fleet(10)
        violations = policy.evaluate(current_fleet_size=0)
        assert len(violations) == 0


class TestGovernedReplicationEngine:
    def _make_engine(self):
        from src.edge_compute.governed_replication import GovernedReplicationEngine

        return GovernedReplicationEngine(secret_key="test-key", max_fleet=5)

    def test_successful_replication(self):
        engine = self._make_engine()
        token = engine.issue_token("admin", "node-1", max_replicas=3)
        params = {"W": np.random.randn(4, 4).astype(np.float32)}
        result = engine.replicate("node-1", params, token)
        assert result.get("success") is True
        assert len(engine.list_active()) == 1

    def test_denied_invalid_token(self):
        engine = self._make_engine()
        fake_token = {"token_id": "fake", "signature": "bad", "expires_at": "2099-01-01T00:00:00+00:00"}
        params = {"W": np.random.randn(4, 4).astype(np.float32)}
        result = engine.replicate("node-1", params, fake_token)
        assert "error" in result
        assert result["gate"] == "crypto_auth"

    def test_denied_subject_mismatch(self):
        engine = self._make_engine()
        token = engine.issue_token("admin", "node-1")
        params = {"W": np.random.randn(4, 4).astype(np.float32)}
        result = engine.replicate("node-DIFFERENT", params, token)
        assert "error" in result

    def test_kill_switch(self):
        engine = self._make_engine()
        token = engine.issue_token("admin", "node-1", max_replicas=3)
        params = {"W": np.random.randn(4, 4).astype(np.float32)}
        result = engine.replicate("node-1", params, token)
        replica_id = result["replica"]["replica_id"]

        kill_token = engine.issue_token("admin", "admin")
        kill_result = engine.kill_replica(replica_id, kill_token)
        assert kill_result["success"] is True
        assert len(engine.list_active()) == 0

    def test_quarantine(self):
        engine = self._make_engine()
        token = engine.issue_token("admin", "node-1")
        params = {"W": np.random.randn(4, 4).astype(np.float32)}
        result = engine.replicate("node-1", params, token)
        replica_id = result["replica"]["replica_id"]

        q_token = engine.issue_token("admin", "admin")
        q_result = engine.quarantine_replica(replica_id, q_token, "suspicious behavior")
        assert q_result["success"] is True
        assert len(engine.list_quarantined()) == 1

    def test_fleet_limit_enforced(self):
        engine = self._make_engine()  # max_fleet=5
        params = {"W": np.random.randn(4, 4).astype(np.float32)}
        for i in range(5):
            token = engine.issue_token("admin", f"node-{i}", max_replicas=10)
            engine.replicate(f"node-{i}", params, token)
        # 6th should fail
        token = engine.issue_token("admin", "node-5", max_replicas=10)
        result = engine.replicate("node-5", params, token)
        assert "error" in result
        assert result["gate"] == "policy"

    def test_audit_trail(self):
        engine = self._make_engine()
        token = engine.issue_token("admin", "node-1")
        params = {"W": np.random.randn(4, 4).astype(np.float32)}
        engine.replicate("node-1", params, token)
        assert len(engine._audit_log) >= 2  # token_issued + replication_executed


# ═══════════════════════════════════════════════════════════
# Data Value Assessor Tests
# ═══════════════════════════════════════════════════════════


class TestRuleBasedAssessor:
    def test_military_text_valuable(self):
        from src.edge_compute.data_value_assessor import RuleBasedAssessor

        assessor = RuleBasedAssessor()
        is_val, conf = assessor.assess("Enemy UAV detected near convoy")
        assert is_val is True
        assert conf > 0.0

    def test_irrelevant_text_not_valuable(self):
        from src.edge_compute.data_value_assessor import RuleBasedAssessor

        assessor = RuleBasedAssessor()
        is_val, _ = assessor.assess("The weather is nice today")
        assert is_val is False

    def test_arabic_keywords(self):
        from src.edge_compute.data_value_assessor import RuleBasedAssessor

        assessor = RuleBasedAssessor()
        is_val, _ = assessor.assess("تم رصد تهديد في المنطقة")  # "Threat detected in the area"
        assert is_val is True

    def test_numeric_anomaly(self):
        from src.edge_compute.data_value_assessor import RuleBasedAssessor

        assessor = RuleBasedAssessor()
        is_val, _ = assessor.assess(5.0)  # > 3 sigma
        assert is_val is True
        is_val2, _ = assessor.assess(0.5)
        assert is_val2 is False

    def test_custom_rule(self):
        from src.edge_compute.data_value_assessor import RuleBasedAssessor

        assessor = RuleBasedAssessor()
        assessor.add_custom_rule(lambda x: isinstance(x, list) and len(x) > 10)
        is_val, _ = assessor.assess(list(range(20)))
        assert is_val is True


class TestStatisticalAssessor:
    def test_high_entropy_valuable(self):
        from src.edge_compute.data_value_assessor import StatisticalAssessor

        assessor = StatisticalAssessor(entropy_threshold=0.5)
        # Uniform probs = max entropy
        probs = np.array([0.25, 0.25, 0.25, 0.25])
        is_val, _ = assessor.assess_from_probs(probs)
        assert is_val is True

    def test_low_entropy_not_valuable(self):
        from src.edge_compute.data_value_assessor import StatisticalAssessor

        assessor = StatisticalAssessor(entropy_threshold=0.5)
        # Very confident = low entropy
        probs = np.array([0.99, 0.003, 0.003, 0.004])
        is_val, _ = assessor.assess_from_probs(probs)
        assert is_val is False


class TestDataValueEngine:
    def test_ingest_and_tag(self):
        from src.edge_compute.data_value_assessor import DataValueEngine

        engine = DataValueEngine(cleaning_mode="manual")
        item = engine.ingest("Hostile drone detected", source="sigint")
        assert item.tag == "valuable"
        item2 = engine.ingest("Random noise data", source="test")
        assert item2.tag == "non_valuable"

    def test_self_cleaning_post_cycle(self):
        from src.edge_compute.data_value_assessor import DataValueEngine

        engine = DataValueEngine(cleaning_mode="post_cycle")
        engine.ingest("Enemy target acquired")  # valuable
        engine.ingest("Irrelevant data point")  # non-valuable
        engine.ingest("More noise")  # non-valuable
        stats_before = engine.store.stats()
        assert stats_before["non_valuable"] >= 1
        cleaned = engine.post_cycle_clean()
        assert cleaned >= 1
        stats_after = engine.store.stats()
        assert stats_after["non_valuable"] == 0

    def test_get_training_data_only_valuable(self):
        from src.edge_compute.data_value_assessor import DataValueEngine

        engine = DataValueEngine(cleaning_mode="manual")
        engine.ingest("Missile launch detected")
        engine.ingest("Nice weather")
        training = engine.get_training_data()
        assert len(training) == 1
        assert "Missile" in training[0] or "missile" in training[0].lower()

    def test_batch_ingest(self):
        from src.edge_compute.data_value_assessor import DataValueEngine

        engine = DataValueEngine(cleaning_mode="manual")
        data = [
            "Enemy UAV spotted",
            "Random text",
            "Threat level elevated",
            "Nice day",
            "Hostile convoy approaching",
        ]
        counts = engine.ingest_batch(data, source="batch")
        assert counts["valuable"] >= 2
        assert counts["non_valuable"] >= 1

    def test_reassessment(self):
        from src.edge_compute.data_value_assessor import DataValueEngine

        engine = DataValueEngine(cleaning_mode="manual")
        engine.ingest("some data")
        result = engine.reassess_all()
        assert "unchanged" in result

    def test_immediate_cleaning(self):
        from src.edge_compute.data_value_assessor import DataValueEngine

        engine = DataValueEngine(cleaning_mode="immediate")
        engine.ingest("Random non-military text")
        # Should be cleaned immediately
        assert engine.store.stats()["non_valuable"] == 0

    def test_health_check(self):
        from src.edge_compute.data_value_assessor import DataValueEngine

        engine = DataValueEngine()
        health = engine.health_check()
        assert "cleaning_mode" in health
        assert "store" in health
        assert "rule_keywords" in health


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
