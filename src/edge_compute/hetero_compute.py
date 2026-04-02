"""
S3M Heterogeneous Compute Engine
UNCLASSIFIED - FOUO

Provides seamless two-way compute exchange between CPU and GPU environments.
Compatible with PyTorch when available and degrades to pure-numpy execution.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from src.edge_compute.models import (
    ComputeTask,
    DeviceStats,
    DeviceType,
    OperationType,
    SchedulerDecision,
    SchedulingPolicy,
)

logger = logging.getLogger("s3m.edge.hetero_compute")


class DeviceCapabilities:
    """Detect and cache local device capabilities for secure offline routing."""

    def __init__(self) -> None:
        self.gpu_available = False
        self.gpu_name = ""
        self.gpu_memory_mb = 0.0
        self.cuda_version = ""
        self.cpu_cores = 1
        self.unified_memory_supported = False
        self._detect()

    def _detect(self) -> None:
        self.cpu_cores = os.cpu_count() or 1
        try:
            import torch
        except ImportError:
            logger.info("PyTorch not available; CPU-only mode.")
            return

        try:
            self.gpu_available = bool(torch.cuda.is_available())
            if self.gpu_available:
                self.gpu_name = str(torch.cuda.get_device_name(0))
                props = torch.cuda.get_device_properties(0)
                self.gpu_memory_mb = float(props.total_memory) / 1e6
                self.cuda_version = str(getattr(torch.version, "cuda", "") or "")
                # Tactical edge boards (e.g., Jetson) typically expose UM primitives.
                self.unified_memory_supported = bool(hasattr(torch.cuda, "mem_get_info"))
        except Exception as exc:
            logger.warning("Failed GPU capability probe; defaulting to CPU-only. err=%s", exc)
            self.gpu_available = False
            self.unified_memory_supported = False

        logger.info(
            "DeviceCapabilities: gpu=%s (%s), cores=%d, unified_mem=%s",
            self.gpu_available,
            self.gpu_name,
            self.cpu_cores,
            self.unified_memory_supported,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gpu_available": self.gpu_available,
            "gpu_name": self.gpu_name,
            "gpu_memory_mb": self.gpu_memory_mb,
            "cuda_version": self.cuda_version,
            "cpu_cores": self.cpu_cores,
            "unified_memory_supported": self.unified_memory_supported,
        }


class MemoryManager:
    """
    Manages CPU<->GPU transfer strategy:
      - Unified memory style flow when CUDA UM support is present
      - Pinned-memory transfer fallback
      - Pure numpy fallback if GPU/PyTorch are unavailable
    """

    def __init__(self, caps: DeviceCapabilities):
        self.caps = caps
        self._torch_module: Any = None
        try:
            import torch

            self._torch_module = torch
        except ImportError:
            self._torch_module = None

    def to_device(self, data: Any, device: DeviceType | str) -> Any:
        target = DeviceType.from_value(device)
        if target == DeviceType.CPU:
            return self._to_cpu(data)
        if target == DeviceType.GPU:
            return self._to_gpu(data)
        return data

    def _to_cpu(self, data: Any) -> Any:
        torch = self._torch_module
        if torch is not None and isinstance(data, torch.Tensor):
            return data.cpu()
        return data

    def _to_gpu(self, data: Any) -> Any:
        if not self.caps.gpu_available:
            return data

        torch = self._torch_module
        if torch is None:
            return data

        if isinstance(data, np.ndarray):
            tensor = torch.from_numpy(data)
            if not self.caps.unified_memory_supported and hasattr(tensor, "pin_memory"):
                tensor = tensor.pin_memory()
            return tensor.cuda(non_blocking=True)

        if isinstance(data, torch.Tensor):
            if data.is_cuda:
                return data
            tensor = data
            if not self.caps.unified_memory_supported and hasattr(tensor, "pin_memory"):
                tensor = tensor.pin_memory()
            return tensor.cuda(non_blocking=True)

        return data

    def prefetch(self, data: Any, device: DeviceType | str) -> None:
        """Best-effort prefetch hint; safe no-op when unsupported."""
        target = DeviceType.from_value(device)
        if target != DeviceType.GPU:
            return
        if not self.caps.gpu_available or self._torch_module is None:
            return
        try:
            torch = self._torch_module
            if isinstance(data, torch.Tensor) and data.is_cuda:
                torch.cuda.current_stream().synchronize()
        except Exception:
            return

    def estimate_transfer_time_ms(self, size_bytes: int, direction: str = "h2d") -> float:
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise ValueError("size_bytes must be a non-negative integer")
        if direction not in {"h2d", "d2h"}:
            raise ValueError("direction must be 'h2d' or 'd2h'")
        bandwidth_gbps = 50.0 if self.caps.unified_memory_supported else 12.0
        return float((size_bytes / (bandwidth_gbps * 1e9)) * 1000.0)


class AdaptiveScheduler:
    """
    Contextual Thompson-Sampling bandit for device affinity learning.

    Reward weights default to:
      latency 40%, throughput 30%, memory 20%, power 10%.
    """

    def __init__(
        self,
        exploration_rate: float = 0.1,
        learning_rate: float = 0.01,
        reward_weights: Optional[Dict[str, float]] = None,
        history_window: int = 100,
    ):
        if not isinstance(exploration_rate, (int, float)) or exploration_rate < 0:
            raise ValueError("exploration_rate must be non-negative")
        if not isinstance(learning_rate, (int, float)) or learning_rate <= 0:
            raise ValueError("learning_rate must be positive")
        if not isinstance(history_window, int) or history_window <= 0:
            raise ValueError("history_window must be a positive integer")

        self.exploration_rate = float(exploration_rate)
        self.lr = float(learning_rate)
        self.reward_weights = self._validated_weights(reward_weights)
        self.history_window = history_window

        self._alpha: Dict[Tuple[str, str], float] = defaultdict(lambda: 1.0)
        self._beta: Dict[Tuple[str, str], float] = defaultdict(lambda: 1.0)
        self._history: List[SchedulerDecision] = []
        self._step_count = 0

    def _validated_weights(self, reward_weights: Optional[Dict[str, float]]) -> Dict[str, float]:
        base = {
            "latency": 0.4,
            "throughput": 0.3,
            "memory_efficiency": 0.2,
            "power_efficiency": 0.1,
        }
        if reward_weights is None:
            return base
        if not isinstance(reward_weights, dict):
            raise ValueError("reward_weights must be a dictionary")
        merged: Dict[str, float] = dict(base)
        for key, value in reward_weights.items():
            if key not in merged:
                raise ValueError(f"Unsupported reward weight key: {key}")
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"Reward weight '{key}' must be non-negative numeric")
            merged[key] = float(value)
        total = sum(merged.values())
        if total <= 0:
            raise ValueError("reward weights must sum to a positive value")
        return {key: value / total for key, value in merged.items()}

    def choose_device(
        self,
        operation: OperationType | str,
        gpu_available: bool = True,
        gpu_util: float = 0.0,
        cpu_util: float = 0.0,
    ) -> DeviceType:
        op = OperationType.from_value(operation)
        self._step_count += 1

        if not gpu_available:
            return DeviceType.CPU

        gpu_util = float(min(max(gpu_util, 0.0), 1.0))
        cpu_util = float(min(max(cpu_util, 0.0), 1.0))

        eps = self.exploration_rate / (1.0 + (self._step_count / 100.0))
        if np.random.random() < eps:
            return DeviceType.GPU if np.random.random() > 0.5 else DeviceType.CPU

        op_key = op.value
        cpu_sample = float(np.random.beta(self._alpha[(op_key, "cpu")], self._beta[(op_key, "cpu")]))
        gpu_sample = float(np.random.beta(self._alpha[(op_key, "gpu")], self._beta[(op_key, "gpu")]))

        # In tactical edge conditions, avoid routing onto a saturated processor.
        if gpu_util > 0.9:
            gpu_sample *= 0.3
        if cpu_util > 0.9:
            cpu_sample *= 0.3

        return DeviceType.GPU if gpu_sample > cpu_sample else DeviceType.CPU

    def record_outcome(
        self,
        operation: OperationType | str,
        device: DeviceType | str,
        latency_ms: float,
        throughput: float = 0.0,
        memory_used_mb: float = 0.0,
        power_watts: float = 0.0,
        max_latency_ms: float = 1000.0,
    ) -> float:
        op = OperationType.from_value(operation)
        chosen_device = DeviceType.from_value(device)

        for name, value in {
            "latency_ms": latency_ms,
            "throughput": throughput,
            "memory_used_mb": memory_used_mb,
            "power_watts": power_watts,
            "max_latency_ms": max_latency_ms,
        }.items():
            if not isinstance(value, (int, float)) or float(value) < 0:
                raise ValueError(f"{name} must be a non-negative numeric value")
        if max_latency_ms <= 0:
            raise ValueError("max_latency_ms must be > 0")

        lat_reward = max(0.0, 1.0 - (float(latency_ms) / float(max_latency_ms)))
        thr_reward = min(1.0, float(throughput) / 100.0) if throughput > 0 else 0.5
        mem_reward = max(0.0, 1.0 - (float(memory_used_mb) / 8192.0))
        pow_reward = max(0.0, 1.0 - (float(power_watts) / 60.0)) if power_watts > 0 else 0.5

        w = self.reward_weights
        reward = (
            w["latency"] * lat_reward
            + w["throughput"] * thr_reward
            + w["memory_efficiency"] * mem_reward
            + w["power_efficiency"] * pow_reward
        )
        reward = float(np.clip(reward, 0.0, 1.0))

        key = (op.value, chosen_device.value)
        self._alpha[key] += reward * self.lr * 10.0
        self._beta[key] += (1.0 - reward) * self.lr * 10.0

        self._history.append(
            SchedulerDecision(
                task_id="",
                operation=op,
                chosen_device=chosen_device,
                actual_latency_ms=float(latency_ms),
                reward=reward,
            )
        )
        if len(self._history) > self.history_window:
            self._history = self._history[-self.history_window :]

        return reward

    def get_policy_table(self) -> Dict[str, Dict[str, float]]:
        table: Dict[str, Dict[str, float]] = {}
        for operation in OperationType:
            op_key = operation.value
            cpu_alpha = self._alpha[(op_key, "cpu")]
            cpu_beta = self._beta[(op_key, "cpu")]
            gpu_alpha = self._alpha[(op_key, "gpu")]
            gpu_beta = self._beta[(op_key, "gpu")]
            table[op_key] = {
                "cpu": round(cpu_alpha / (cpu_alpha + cpu_beta), 4),
                "gpu": round(gpu_alpha / (gpu_alpha + gpu_beta), 4),
            }
        return table

    def health_check(self) -> Dict[str, Any]:
        return {
            "step_count": self._step_count,
            "history_size": len(self._history),
            "exploration_rate": self.exploration_rate,
            "learning_rate": self.lr,
            "reward_weights": dict(self.reward_weights),
            "policy_table": self.get_policy_table(),
        }


class HeterogeneousComputeEngine:
    """Main class for seamless two-way CPU/GPU operation exchange."""

    def __init__(
        self,
        policy: SchedulingPolicy | str = SchedulingPolicy.ADAPTIVE,
        reward_weights: Optional[Dict[str, float]] = None,
    ):
        self.policy = SchedulingPolicy.from_value(policy)
        self.caps = DeviceCapabilities()
        self.memory = MemoryManager(self.caps)
        self.scheduler = AdaptiveScheduler(reward_weights=reward_weights)

        self._cpu_stats = DeviceStats(device=DeviceType.CPU)
        self._gpu_stats = DeviceStats(device=DeviceType.GPU)
        self._total_tasks = 0

        self._cpu_ops = {
            OperationType.TOKENIZATION,
            OperationType.PREPROCESSING,
            OperationType.POSTPROCESSING,
            OperationType.IO,
            OperationType.EVALUATION,
        }
        self._gpu_ops = {
            OperationType.MATMUL,
            OperationType.CONV,
            OperationType.ATTENTION,
            OperationType.TRAINING_STEP,
            OperationType.EMBEDDING,
            OperationType.INFERENCE,
        }

        logger.info(
            "HeterogeneousComputeEngine initialized: policy=%s, gpu=%s",
            self.policy.value,
            self.caps.gpu_available,
        )

    def execute(
        self,
        operation: OperationType | str,
        func: Callable[..., Any],
        *args: Any,
        device: Optional[DeviceType | str] = None,
        **kwargs: Any,
    ) -> Any:
        if not callable(func):
            raise ValueError("func must be callable")
        op = OperationType.from_value(operation)

        chosen: DeviceType
        if device is not None and DeviceType.from_value(device) != DeviceType.AUTO:
            chosen = DeviceType.from_value(device)
        else:
            chosen = self._route(op)

        start = time.perf_counter()
        try:
            result = self._run_on_device(chosen, func, args, kwargs)
        except Exception as primary_exc:
            logger.error("Execution failed on %s: %s", chosen.value, primary_exc)
            self._mark_failure(chosen)
            fallback = DeviceType.CPU if chosen == DeviceType.GPU else DeviceType.GPU
            if fallback == DeviceType.GPU and not self.caps.gpu_available:
                raise
            logger.info("Falling back to %s after failure.", fallback.value)
            try:
                result = self._run_on_device(fallback, func, args, kwargs)
                chosen = fallback
            except Exception as fallback_exc:
                self._mark_failure(fallback)
                raise RuntimeError(
                    f"Execution failed on both {chosen.value} and {fallback.value}"
                ) from fallback_exc

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        self._update_stats(chosen, elapsed_ms)
        self._total_tasks += 1

        if self.policy == SchedulingPolicy.ADAPTIVE:
            self.scheduler.record_outcome(operation=op, device=chosen, latency_ms=elapsed_ms)

        return result

    def _run_on_device(
        self,
        target: DeviceType,
        func: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> Any:
        transferred_args = tuple(self._maybe_transfer(item, target) for item in args)
        transferred_kwargs = {key: self._maybe_transfer(value, target) for key, value in kwargs.items()}
        return func(*transferred_args, **transferred_kwargs)

    def _route(self, operation: OperationType | str) -> DeviceType:
        op = OperationType.from_value(operation)

        if self.policy == SchedulingPolicy.PREFER_GPU:
            return DeviceType.GPU if self.caps.gpu_available else DeviceType.CPU
        if self.policy == SchedulingPolicy.PREFER_CPU:
            return DeviceType.CPU
        if self.policy == SchedulingPolicy.ROUND_ROBIN:
            if not self.caps.gpu_available:
                return DeviceType.CPU
            return DeviceType.GPU if (self._total_tasks % 2 == 0) else DeviceType.CPU
        if self.policy == SchedulingPolicy.ADAPTIVE:
            return self.scheduler.choose_device(
                operation=op,
                gpu_available=self.caps.gpu_available,
                gpu_util=self._gpu_stats.utilization_pct / 100.0,
                cpu_util=self._cpu_stats.utilization_pct / 100.0,
            )
        return DeviceType.GPU if (op in self._gpu_ops and self.caps.gpu_available) else DeviceType.CPU

    def _maybe_transfer(self, data: Any, target: DeviceType) -> Any:
        if isinstance(data, np.ndarray):
            return self.memory.to_device(data, target)
        try:
            import torch
        except ImportError:
            return data
        if isinstance(data, torch.Tensor):
            return self.memory.to_device(data, target)
        return data

    def _mark_failure(self, device: DeviceType) -> None:
        stats = self._gpu_stats if device == DeviceType.GPU else self._cpu_stats
        stats.failed_tasks += 1

    def _update_stats(self, device: DeviceType, latency_ms: float) -> None:
        stats = self._gpu_stats if device == DeviceType.GPU else self._cpu_stats
        n = stats.tasks_completed
        stats.avg_latency_ms = ((stats.avg_latency_ms * n) + float(latency_ms)) / float(n + 1)
        stats.tasks_completed += 1

    def execute_batch(
        self,
        tasks: List[ComputeTask],
        func_map: Dict[OperationType, Callable[..., Any]],
        data_map: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(tasks, list):
            raise ValueError("tasks must be a list")
        if not isinstance(func_map, dict):
            raise ValueError("func_map must be a dictionary")
        if not isinstance(data_map, dict):
            raise ValueError("data_map must be a dictionary")

        results: Dict[str, Any] = {}
        for task in tasks:
            if not isinstance(task, ComputeTask):
                raise ValueError("tasks must contain ComputeTask entries")

            func = func_map.get(task.operation)
            if func is None:
                logger.warning("No function registered for operation=%s", task.operation.value)
                continue
            if task.task_id not in data_map:
                logger.warning("No data payload for task_id=%s", task.task_id)
                continue

            explicit_device: Optional[DeviceType]
            if task.assigned_device == DeviceType.AUTO:
                explicit_device = None
            else:
                explicit_device = task.assigned_device

            results[task.task_id] = self.execute(
                task.operation,
                func,
                data_map[task.task_id],
                device=explicit_device,
            )
        return results

    def device_stats(self) -> Dict[str, Any]:
        return {
            "cpu": self._cpu_stats.model_dump(),
            "gpu": self._gpu_stats.model_dump(),
            "total_tasks": self._total_tasks,
        }

    def health_check(self) -> Dict[str, Any]:
        return {
            "policy": self.policy.value,
            "capabilities": self.caps.to_dict(),
            "total_tasks": self._total_tasks,
            "scheduler": self.scheduler.health_check()
            if self.policy == SchedulingPolicy.ADAPTIVE
            else {},
            "cpu_stats": self._cpu_stats.model_dump(),
            "gpu_stats": self._gpu_stats.model_dump(),
        }
