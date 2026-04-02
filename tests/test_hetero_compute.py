"""Unit tests for S3M heterogeneous CPU/GPU compute engine."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pytest

from src.edge_compute.hetero_compute import AdaptiveScheduler, HeterogeneousComputeEngine, MemoryManager
from src.edge_compute.models import ComputeTask, DeviceType, OperationType, SchedulingPolicy


class _CapsStub:
    """Minimal capability stub for isolated offline tests."""

    def __init__(self, *, gpu_available: bool, unified_memory_supported: bool) -> None:
        self.gpu_available = gpu_available
        self.unified_memory_supported = unified_memory_supported
        self.gpu_name = "stub"
        self.gpu_memory_mb = 1024.0
        self.cuda_version = "stub"
        self.cpu_cores = 8


class _FakeTensor:
    def __init__(self, arr: np.ndarray):
        self.arr = arr
        self.pinned = False
        self.cuda_called = False
        self.is_cuda = False

    def pin_memory(self) -> "_FakeTensor":
        self.pinned = True
        return self

    def cuda(self, non_blocking: bool = True) -> "_FakeTensor":
        del non_blocking
        self.cuda_called = True
        self.is_cuda = True
        return self

    def cpu(self) -> "_FakeTensor":
        self.is_cuda = False
        return self


class _FakeTorch:
    Tensor = _FakeTensor

    @staticmethod
    def from_numpy(arr: np.ndarray) -> _FakeTensor:
        return _FakeTensor(arr)


def test_models_validation_and_serialization() -> None:
    task = ComputeTask(
        task_id="t-1",
        operation=OperationType.MATMUL,
        assigned_device=DeviceType.AUTO,
        payload_size_bytes=256,
        metadata={"priority": "high"},
    )
    payload = task.to_dict()
    assert payload["task_id"] == "t-1"
    assert payload["operation"] == "matmul"
    assert payload["assigned_device"] == "auto"

    with pytest.raises(ValueError):
        ComputeTask(task_id="", operation=OperationType.IO)


def test_memory_manager_keeps_numpy_when_gpu_unavailable() -> None:
    manager = MemoryManager(_CapsStub(gpu_available=False, unified_memory_supported=False))
    arr = np.array([1.0, 2.0], dtype=np.float32)
    moved = manager.to_device(arr, DeviceType.GPU)
    assert isinstance(moved, np.ndarray)
    assert np.array_equal(moved, arr)


def test_memory_manager_uses_pinned_fallback_when_unified_unavailable() -> None:
    manager = MemoryManager(_CapsStub(gpu_available=True, unified_memory_supported=False))
    manager._torch_module = _FakeTorch()
    arr = np.array([1.0, 2.0], dtype=np.float32)
    moved = manager.to_device(arr, DeviceType.GPU)
    assert isinstance(moved, _FakeTensor)
    assert moved.pinned is True
    assert moved.cuda_called is True


def test_memory_manager_unified_path_skips_pinning() -> None:
    manager = MemoryManager(_CapsStub(gpu_available=True, unified_memory_supported=True))
    manager._torch_module = _FakeTorch()
    arr = np.array([1.0, 2.0], dtype=np.float32)
    moved = manager.to_device(arr, DeviceType.GPU)
    assert isinstance(moved, _FakeTensor)
    assert moved.pinned is False
    assert moved.cuda_called is True


def test_scheduler_prefers_rewarded_device_with_thompson_backbone(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler = AdaptiveScheduler(exploration_rate=0.0, learning_rate=0.5)

    # Deterministic TS sampling for repeatable offline tests.
    monkeypatch.setattr(np.random, "beta", lambda a, b: float(a) / float(a + b))
    monkeypatch.setattr(np.random, "random", lambda: 0.99)

    for _ in range(20):
        scheduler.record_outcome(
            operation=OperationType.MATMUL,
            device=DeviceType.GPU,
            latency_ms=10.0,
            throughput=120.0,
            memory_used_mb=400.0,
            power_watts=10.0,
        )
    for _ in range(8):
        scheduler.record_outcome(
            operation=OperationType.MATMUL,
            device=DeviceType.CPU,
            latency_ms=700.0,
            throughput=10.0,
            memory_used_mb=1800.0,
            power_watts=40.0,
        )

    choice = scheduler.choose_device(OperationType.MATMUL, gpu_available=True)
    assert choice == DeviceType.GPU
    table = scheduler.get_policy_table()["matmul"]
    assert table["gpu"] > table["cpu"]


def test_scheduler_forces_cpu_when_gpu_absent() -> None:
    scheduler = AdaptiveScheduler(exploration_rate=0.0)
    chosen = scheduler.choose_device(OperationType.ATTENTION, gpu_available=False)
    assert chosen == DeviceType.CPU


def test_engine_routing_policies_and_round_robin() -> None:
    engine_gpu = HeterogeneousComputeEngine(policy=SchedulingPolicy.PREFER_GPU)
    engine_gpu.caps.gpu_available = True
    assert engine_gpu._route(OperationType.CONV) == DeviceType.GPU

    engine_cpu = HeterogeneousComputeEngine(policy=SchedulingPolicy.PREFER_CPU)
    engine_cpu.caps.gpu_available = True
    assert engine_cpu._route(OperationType.CONV) == DeviceType.CPU

    engine_rr = HeterogeneousComputeEngine(policy=SchedulingPolicy.ROUND_ROBIN)
    engine_rr.caps.gpu_available = True
    assert engine_rr._route(OperationType.MATMUL) == DeviceType.GPU
    engine_rr._total_tasks = 1
    assert engine_rr._route(OperationType.MATMUL) == DeviceType.CPU


def test_engine_fallback_when_primary_device_fails() -> None:
    engine = HeterogeneousComputeEngine(policy=SchedulingPolicy.PREFER_GPU)
    engine.caps.gpu_available = True

    calls: List[DeviceType] = []

    def fake_run(
        target: DeviceType,
        func: Any,
        args: tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> Any:
        del args, kwargs
        calls.append(target)
        if target == DeviceType.GPU:
            raise RuntimeError("gpu failed")
        return func()

    engine._run_on_device = fake_run  # type: ignore[assignment]

    result = engine.execute(OperationType.MATMUL, lambda: "ok")
    assert result == "ok"
    assert calls == [DeviceType.GPU, DeviceType.CPU]
    assert engine.device_stats()["gpu"]["failed_tasks"] == 1


def test_engine_execute_batch_and_health() -> None:
    engine = HeterogeneousComputeEngine(policy=SchedulingPolicy.ADAPTIVE)
    engine.caps.gpu_available = False

    tasks = [
        ComputeTask(task_id="a", operation=OperationType.TOKENIZATION),
        ComputeTask(task_id="b", operation=OperationType.MATMUL),
        ComputeTask(task_id="missing", operation=OperationType.IO),
    ]
    func_map = {
        OperationType.TOKENIZATION: lambda x: str(x).upper(),
        OperationType.MATMUL: lambda x: x * 2,
    }
    data_map = {"a": "abc", "b": 5}

    out = engine.execute_batch(tasks=tasks, func_map=func_map, data_map=data_map)
    assert out == {"a": "ABC", "b": 10}

    health = engine.health_check()
    assert health["policy"] == "adaptive"
    assert "scheduler" in health
    assert health["cpu_stats"]["tasks_completed"] >= 2

