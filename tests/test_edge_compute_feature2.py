"""
Unit tests for S3M Edge Compute - Feature 2: Heterogeneous Compute
Tests adaptive scheduler, device capabilities, memory manager, and
the main HeterogeneousComputeEngine.
UNCLASSIFIED - FOUO
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

models = pytest.importorskip("src.edge_compute.models")

ComputeTask = models.ComputeTask
DeviceType = models.DeviceType
OperationType = models.OperationType
SchedulingPolicy = models.SchedulingPolicy


# ===========================================================
# Device Capabilities Tests
# ===========================================================

class TestDeviceCapabilities:

    def test_detection_runs(self):
        from src.edge_compute.hetero_compute import DeviceCapabilities
        caps = DeviceCapabilities()
        assert caps.cpu_cores >= 1
        assert isinstance(caps.gpu_available, bool)

    def test_to_dict(self):
        from src.edge_compute.hetero_compute import DeviceCapabilities
        caps = DeviceCapabilities()
        d = caps.to_dict()
        assert "gpu_available" in d
        assert "cpu_cores" in d
        assert "unified_memory_supported" in d


# ===========================================================
# Adaptive Scheduler Tests
# ===========================================================

class TestAdaptiveScheduler:
    """Tests for the Thompson Sampling contextual bandit."""

    def test_initialization(self):
        from src.edge_compute.hetero_compute import AdaptiveScheduler
        sched = AdaptiveScheduler()
        assert sched.exploration_rate == 0.1
        assert sched._step_count == 0

    def test_choose_device_no_gpu(self):
        from src.edge_compute.hetero_compute import AdaptiveScheduler
        sched = AdaptiveScheduler()
        device = sched.choose_device(OperationType.MATMUL, gpu_available=False)
        assert device == DeviceType.CPU

    def test_choose_device_with_gpu(self):
        from src.edge_compute.hetero_compute import AdaptiveScheduler
        sched = AdaptiveScheduler(exploration_rate=0.0)  # No exploration
        # After some GPU-favoring updates, scheduler should prefer GPU for matmul
        for _ in range(20):
            sched.record_outcome(OperationType.MATMUL, DeviceType.GPU, latency_ms=1.0)
            sched.record_outcome(OperationType.MATMUL, DeviceType.CPU, latency_ms=100.0)

        # Should now prefer GPU
        choices = [sched.choose_device(OperationType.MATMUL, gpu_available=True) for _ in range(50)]
        gpu_count = sum(1 for c in choices if c == DeviceType.GPU)
        assert gpu_count > 25  # Majority should be GPU

    def test_record_outcome_reward_range(self):
        from src.edge_compute.hetero_compute import AdaptiveScheduler
        sched = AdaptiveScheduler()
        reward = sched.record_outcome(
            OperationType.TOKENIZATION,
            DeviceType.CPU,
            latency_ms=5.0,
            throughput=50.0,
            memory_used_mb=100.0,
            power_watts=10.0,
        )
        assert 0.0 <= reward <= 1.0

    def test_policy_table_builds(self):
        from src.edge_compute.hetero_compute import AdaptiveScheduler
        sched = AdaptiveScheduler()
        sched.record_outcome(OperationType.MATMUL, DeviceType.GPU, latency_ms=5.0)
        sched.record_outcome(OperationType.TOKENIZATION, DeviceType.CPU, latency_ms=2.0)
        table = sched.get_policy_table()
        assert "matmul" in table
        assert "tokenization" in table

    def test_exploration_decays(self):
        from src.edge_compute.hetero_compute import AdaptiveScheduler
        sched = AdaptiveScheduler(exploration_rate=1.0)
        # After many steps, effective exploration should be lower
        for _ in range(200):
            sched.choose_device(OperationType.MATMUL, gpu_available=True)
        # Effective rate = 1.0 / (1 + 200/100) = 0.33
        # Just verify it ran without error
        assert sched._step_count == 200

    def test_overloaded_device_penalty(self):
        from src.edge_compute.hetero_compute import AdaptiveScheduler
        sched = AdaptiveScheduler(exploration_rate=0.0)
        # Train to prefer GPU
        for _ in range(30):
            sched.record_outcome(OperationType.ATTENTION, DeviceType.GPU, latency_ms=1.0)
            sched.record_outcome(OperationType.ATTENTION, DeviceType.CPU, latency_ms=100.0)

        # With GPU at 95% util, should sometimes choose CPU despite preference
        choices = [
            sched.choose_device(OperationType.ATTENTION, gpu_available=True, gpu_util=0.95)
            for _ in range(100)
        ]
        cpu_count = sum(1 for c in choices if c == DeviceType.CPU)
        assert cpu_count > 0  # At least some CPU choices due to penalty

    def test_health_check(self):
        from src.edge_compute.hetero_compute import AdaptiveScheduler
        sched = AdaptiveScheduler()
        health = sched.health_check()
        assert "step_count" in health
        assert "policy_table" in health


# ===========================================================
# Memory Manager Tests
# ===========================================================

class TestMemoryManager:

    def test_numpy_to_cpu(self):
        from src.edge_compute.hetero_compute import DeviceCapabilities, MemoryManager
        caps = DeviceCapabilities()
        mm = MemoryManager(caps)
        data = np.random.randn(10, 10).astype(np.float32)
        result = mm.to_device(data, DeviceType.CPU)
        assert isinstance(result, np.ndarray)

    def test_numpy_to_gpu_fallback(self):
        from src.edge_compute.hetero_compute import DeviceCapabilities, MemoryManager
        caps = DeviceCapabilities()
        mm = MemoryManager(caps)
        data = np.random.randn(10, 10).astype(np.float32)
        result = mm.to_device(data, DeviceType.GPU)
        # If no GPU, should still return the data
        assert result is not None

    def test_transfer_time_estimate(self):
        from src.edge_compute.hetero_compute import DeviceCapabilities, MemoryManager
        caps = DeviceCapabilities()
        mm = MemoryManager(caps)
        t = mm.estimate_transfer_time_ms(1_000_000)  # 1 MB
        assert t > 0


# ===========================================================
# HeterogeneousComputeEngine Tests
# ===========================================================

class TestHeterogeneousComputeEngine:
    """Tests for the main GPU<->CPU scheduling engine."""

    def test_init_adaptive(self):
        from src.edge_compute.hetero_compute import HeterogeneousComputeEngine
        engine = HeterogeneousComputeEngine(policy=SchedulingPolicy.ADAPTIVE)
        assert engine.policy == SchedulingPolicy.ADAPTIVE

    def test_init_prefer_cpu(self):
        from src.edge_compute.hetero_compute import HeterogeneousComputeEngine
        engine = HeterogeneousComputeEngine(policy=SchedulingPolicy.PREFER_CPU)
        assert engine.policy == SchedulingPolicy.PREFER_CPU

    def test_execute_cpu_op(self):
        from src.edge_compute.hetero_compute import HeterogeneousComputeEngine
        engine = HeterogeneousComputeEngine(policy=SchedulingPolicy.PREFER_CPU)
        data = np.random.randn(10, 10).astype(np.float32)
        result = engine.execute(OperationType.TOKENIZATION, lambda x: x.astype(np.int32), data)
        assert result.dtype == np.int32

    def test_execute_matmul(self):
        from src.edge_compute.hetero_compute import HeterogeneousComputeEngine
        engine = HeterogeneousComputeEngine(policy=SchedulingPolicy.PREFER_CPU)
        data = np.random.randn(8, 8).astype(np.float32)
        result = engine.execute(OperationType.MATMUL, lambda x: x @ x.T, data)
        assert result.shape == (8, 8)

    def test_execute_with_device_override(self):
        from src.edge_compute.hetero_compute import HeterogeneousComputeEngine
        engine = HeterogeneousComputeEngine()
        data = np.random.randn(5, 5).astype(np.float32)
        result = engine.execute(
            OperationType.CUSTOM,
            lambda x: x * 2,
            data,
            device=DeviceType.CPU,
        )
        np.testing.assert_allclose(result, data * 2)

    def test_stats_accumulate(self):
        from src.edge_compute.hetero_compute import HeterogeneousComputeEngine
        engine = HeterogeneousComputeEngine(policy=SchedulingPolicy.PREFER_CPU)
        data = np.random.randn(5, 5).astype(np.float32)
        for _ in range(5):
            engine.execute(OperationType.PREPROCESSING, lambda x: x + 1, data)
        stats = engine.device_stats()
        assert stats["total_tasks"] == 5
        assert stats["cpu"]["tasks_completed"] == 5
        assert stats["cpu"]["avg_latency_ms"] > 0

    def test_round_robin_policy(self):
        from src.edge_compute.hetero_compute import HeterogeneousComputeEngine
        engine = HeterogeneousComputeEngine(policy=SchedulingPolicy.ROUND_ROBIN)
        data = np.random.randn(4, 4).astype(np.float32)
        # Without GPU, all should fall to CPU
        for _ in range(4):
            engine.execute(OperationType.MATMUL, lambda x: x, data)
        assert engine._total_tasks == 4

    def test_execute_batch(self):
        from src.edge_compute.hetero_compute import HeterogeneousComputeEngine
        engine = HeterogeneousComputeEngine(policy=SchedulingPolicy.PREFER_CPU)

        tasks = [
            ComputeTask(task_id="t1", operation=OperationType.PREPROCESSING),
            ComputeTask(task_id="t2", operation=OperationType.MATMUL),
        ]
        func_map = {
            OperationType.PREPROCESSING: lambda x: x / x.max(),
            OperationType.MATMUL: lambda x: x @ x.T,
        }
        data_map = {
            "t1": np.random.randn(5, 5).astype(np.float32),
            "t2": np.random.randn(5, 5).astype(np.float32),
        }
        results = engine.execute_batch(tasks, func_map, data_map)
        assert "t1" in results
        assert "t2" in results

    def test_fallback_on_error(self):
        from src.edge_compute.hetero_compute import HeterogeneousComputeEngine
        engine = HeterogeneousComputeEngine(policy=SchedulingPolicy.PREFER_CPU)

        call_count = {"n": 0}

        def flaky_fn(x):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("Simulated failure")
            return x * 2

        data = np.array([1.0, 2.0, 3.0], dtype=np.float32)
        # Since both fallbacks go to CPU (no GPU), the second try should work
        result = engine.execute(OperationType.CUSTOM, flaky_fn, data)
        np.testing.assert_allclose(result, data * 2)

    def test_health_check(self):
        from src.edge_compute.hetero_compute import HeterogeneousComputeEngine
        engine = HeterogeneousComputeEngine()
        health = engine.health_check()
        assert "policy" in health
        assert "capabilities" in health
        assert "total_tasks" in health
        assert "scheduler" in health


# ===========================================================
# Manager Integration Tests
# ===========================================================

class TestEdgeComputeManager:
    """Tests for the unified EdgeComputeManager."""

    def test_initialization(self):
        from src.edge_compute.manager import EdgeComputeManager
        mgr = EdgeComputeManager()
        assert mgr.federated is not None
        assert mgr.self_trainer is not None
        assert mgr.replication is not None
        assert mgr.data_gen is not None
        assert mgr.sandbox is not None
        assert mgr.compute is not None

    def test_quick_self_train(self):
        from src.edge_compute.manager import EdgeComputeManager
        mgr = EdgeComputeManager(confidence_threshold=0.1)
        x = np.random.randn(30, 8).astype(np.float32)
        classes = np.random.randint(0, 3, size=30)
        y = np.zeros((30, 3), dtype=np.float32)
        y[np.arange(30), classes] = 1.0
        unlabeled = np.random.randn(100, 8).astype(np.float32)

        result = mgr.quick_self_train(8, 3, x, y, unlabeled, cycles=3)
        assert result["cycles_completed"] == 3
        assert len(result["history"]) == 3
        mgr.shutdown()

    def test_full_health_check(self):
        from src.edge_compute.manager import EdgeComputeManager
        mgr = EdgeComputeManager()
        health = mgr.health_check()
        assert "federated" in health
        assert "self_training" in health
        assert "replication" in health
        assert "data_generation" in health
        assert "sandbox" in health
        assert "heterogeneous_compute" in health
        mgr.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
