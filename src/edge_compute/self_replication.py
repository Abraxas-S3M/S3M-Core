"""
S3M Self-Replication Engine
UNCLASSIFIED - FOUO

Enables a trained edge node to autonomously spawn new replicas on
unprovisioned hardware.

Novel approach: "Mitotic Model Division"
  Each replica receives a distilled model tailored to the target node's
  memory/CPU budget instead of a full-weight clone.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional
from uuid import uuid4

import numpy as np

from src.edge_compute.models import NodeStatus, ReplicaSpec

logger = logging.getLogger("s3m.edge.replication")

_ENV_KEY_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class ReplicationEngine:
    """
    Manages the self-replication lifecycle for S3M edge nodes.

    Supports Docker and Podman runtimes. Firecracker support is stubbed
    for future micro-VM tactical isolation.
    """

    def __init__(
        self,
        max_replicas: int = 8,
        default_distillation_ratio: float = 0.6,
        container_runtime: str = "docker",
        bootstrap_image: str = "s3m-edge-node:latest",
        resource_limits: Optional[Dict[str, int]] = None,
    ):
        if max_replicas <= 0:
            raise ValueError("max_replicas must be positive")
        if default_distillation_ratio <= 0 or default_distillation_ratio > 1.0:
            raise ValueError("default_distillation_ratio must be in (0, 1]")
        if not container_runtime.strip():
            raise ValueError("container_runtime must be a non-empty string")
        if not bootstrap_image.strip():
            raise ValueError("bootstrap_image must be a non-empty string")

        self.max_replicas = max_replicas
        self.default_distillation_ratio = default_distillation_ratio
        self.container_runtime = container_runtime
        self.bootstrap_image = bootstrap_image
        self.resource_limits = resource_limits or {
            "cpu_cores": 4,
            "memory_mb": 4096,
            "disk_mb": 8192,
        }

        self._replicas: Dict[str, ReplicaSpec] = {}
        self._replica_workdirs: Dict[str, str] = {}
        self._runtime_available = self._check_runtime()

        logger.info(
            "ReplicationEngine runtime=%s available=%s max_replicas=%d",
            container_runtime,
            self._runtime_available,
            max_replicas,
        )

    # Runtime detection -------------------------------------------------

    def _check_runtime(self) -> bool:
        """Check if the selected container runtime binary is on PATH."""
        return shutil.which(self.container_runtime) is not None

    def _run_cmd(self, cmd: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
        """Execute a runtime command with timeout and captured output."""
        logger.debug("Running command: %s", " ".join(cmd))
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    # Distillation budget calculator -----------------------------------

    @staticmethod
    def compute_distillation_ratio(
        target_memory_mb: int,
        parent_model_size_mb: float,
        min_ratio: float = 0.2,
        max_ratio: float = 1.0,
    ) -> float:
        """
        Compute a memory-safe distillation ratio from target hardware.

        Tactical note:
          Reserve 40% RAM for mission runtime/sensors and only budget
          60% for model weights to preserve battlefield responsiveness.
        """
        if target_memory_mb <= 0:
            raise ValueError("target_memory_mb must be positive")
        if min_ratio <= 0 or max_ratio <= 0 or min_ratio > max_ratio:
            raise ValueError("min_ratio/max_ratio bounds are invalid")

        usable_mb = float(target_memory_mb) * 0.6
        if parent_model_size_mb <= 0:
            return max_ratio
        ratio = usable_mb / parent_model_size_mb
        return float(np.clip(ratio, min_ratio, max_ratio))

    # Model export ------------------------------------------------------

    @staticmethod
    def export_model_snapshot(
        params: Dict[str, np.ndarray],
        output_dir: str,
        model_name: str = "s3m_edge_model",
    ) -> str:
        """Serialize model parameters to .npz for container embedding."""
        if not params:
            raise ValueError("params cannot be empty")
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f"{model_name}.npz")
        np.savez_compressed(path, **params)
        logger.info("Exported model snapshot: %s (%.2f MB)", path, os.path.getsize(path) / 1e6)
        return path

    @staticmethod
    def load_model_snapshot(path: str, dequantize: bool = False) -> Dict[str, np.ndarray]:
        """Load serialized model parameters from a snapshot."""
        params: Dict[str, np.ndarray] = {}
        with np.load(path) as data:
            for key in data.files:
                if key.endswith("__scale"):
                    continue
                arr = data[key]
                scale_key = f"{key}__scale"
                if dequantize and scale_key in data.files and arr.dtype == np.int8:
                    scale = float(data[scale_key][0])
                    params[key] = arr.astype(np.float32) * scale
                else:
                    params[key] = arr
        return params

    # Container lifecycle ----------------------------------------------

    def create_replica(
        self,
        parent_node_id: str,
        parent_params: Dict[str, np.ndarray],
        target_memory_mb: int = 4096,
        target_cpu_cores: int = 4,
        distillation_ratio: Optional[float] = None,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> ReplicaSpec:
        """
        Spawn a new edge replica:
          1. Compute distillation ratio.
          2. Distill + quantize model.
          3. Package model snapshot for runtime.
          4. Launch container with resource limits.
          5. Register replica metadata locally.
        """
        if not isinstance(parent_node_id, str) or not parent_node_id.strip():
            raise ValueError("parent_node_id must be non-empty")
        if not parent_params:
            raise ValueError("parent_params must be a non-empty dict")
        if target_memory_mb <= 0 or target_cpu_cores <= 0:
            raise ValueError("target_memory_mb and target_cpu_cores must be positive")
        self._validate_env_vars(env_vars)

        if len(self._replicas) >= self.max_replicas:
            raise RuntimeError(f"Max replicas ({self.max_replicas}) reached")

        replica_id = str(uuid4())

        parent_size_mb = sum(arr.nbytes for arr in parent_params.values()) / 1e6
        if distillation_ratio is None:
            ratio = (
                self.default_distillation_ratio
                if parent_size_mb <= 0
                else self.compute_distillation_ratio(target_memory_mb, parent_size_mb)
            )
        else:
            if distillation_ratio <= 0 or distillation_ratio > 1.0:
                raise ValueError("distillation_ratio must be in (0, 1]")
            ratio = float(distillation_ratio)

        distilled_params = self._distill_params(parent_params, ratio)
        quantized_params = self._quantize_params(distilled_params)

        work_dir = tempfile.mkdtemp(prefix=f"s3m_replica_{replica_id[:8]}_")
        model_path = self.export_model_snapshot(
            quantized_params,
            work_dir,
            f"replica_{replica_id[:8]}",
        )

        container_id = ""
        if self._runtime_available:
            container_id = self._launch_container(
                replica_id=replica_id,
                model_dir=work_dir,
                cpu_cores=target_cpu_cores,
                memory_mb=target_memory_mb,
                env_vars=env_vars,
            )

        spec = ReplicaSpec(
            replica_id=replica_id,
            parent_node_id=parent_node_id,
            container_id=container_id,
            distillation_ratio=ratio,
            status=NodeStatus.ONLINE if container_id else NodeStatus.OFFLINE,
            resource_limits={
                "cpu_cores": target_cpu_cores,
                "memory_mb": target_memory_mb,
            },
            model_snapshot_path=model_path,
            quantization="int8",
            metadata={
                "parent_model_size_mb": round(parent_size_mb, 3),
                "runtime": self.container_runtime,
            },
        )
        self._replicas[replica_id] = spec
        self._replica_workdirs[replica_id] = work_dir

        logger.info(
            "Replica %s created ratio=%.3f container=%s",
            replica_id[:8],
            ratio,
            container_id[:12] if container_id else "none",
        )
        return spec

    def _distill_params(self, params: Dict[str, np.ndarray], ratio: float) -> Dict[str, np.ndarray]:
        """
        Distill parameters by truncating dimensions.

        Tactical note:
          This preserves a compact mission-capable model on weaker nodes
          so every asset contributes to swarm coverage.
        """
        distilled: Dict[str, np.ndarray] = {}

        for name, arr in params.items():
            if not isinstance(name, str) or not name:
                raise ValueError("all parameter names must be non-empty strings")
            if not isinstance(arr, np.ndarray):
                raise ValueError(f"parameter '{name}' must be np.ndarray")

            if arr.ndim == 0:
                distilled[name] = arr.copy()
                continue

            if arr.ndim >= 2:
                new_shape = list(arr.shape)
                dim_to_cut = int(np.argmin(new_shape))
                new_shape[dim_to_cut] = max(1, int(new_shape[dim_to_cut] * ratio))
                slices = tuple(slice(0, s) for s in new_shape)
                distilled[name] = arr[slices].copy()
            else:
                new_len = max(1, int(arr.shape[0] * ratio))
                distilled[name] = arr[:new_len].copy()

        return distilled

    def _quantize_params(self, params: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """Quantize floating tensors to INT8 for Jetson-class deployment."""
        quantized: Dict[str, np.ndarray] = {}
        for name, arr in params.items():
            if np.issubdtype(arr.dtype, np.floating):
                if arr.size == 0:
                    quantized[name] = arr.astype(np.int8)
                    quantized[f"{name}__scale"] = np.array([1.0], dtype=np.float32)
                    continue
                max_abs = float(np.max(np.abs(arr)))
                scale = max(max_abs / 127.0, 1e-8)
                q = np.clip(np.round(arr / scale), -127, 127).astype(np.int8)
                quantized[name] = q
                quantized[f"{name}__scale"] = np.array([scale], dtype=np.float32)
            else:
                quantized[name] = arr
        return quantized

    def _launch_container(
        self,
        replica_id: str,
        model_dir: str,
        cpu_cores: int,
        memory_mb: int,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> str:
        """Launch a container with the distilled model mounted read-only."""
        container_name = f"s3m-edge-{replica_id[:8]}"
        cmd = [
            self.container_runtime,
            "run",
            "-d",
            "--name",
            container_name,
            f"--cpus={cpu_cores}",
            f"--memory={memory_mb}m",
            "--network=host",
            "--read-only",
            "-v",
            f"{model_dir}:/opt/s3m/models:ro",
            "-e",
            f"S3M_NODE_ID={replica_id}",
        ]

        if env_vars:
            for key, value in env_vars.items():
                cmd.extend(["-e", f"{key}={value}"])

        cmd.append(self.bootstrap_image)

        try:
            result = self._run_cmd(cmd)
            if result.returncode == 0:
                container_id = result.stdout.strip()[:64]
                logger.info("Container launched: %s", container_id[:12])
                return container_id
            logger.error("Container launch failed: %s", result.stderr.strip())
            return ""
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.error("Container runtime error: %s", exc)
            return ""

    def stop_replica(self, replica_id: str) -> bool:
        """Stop and remove a replica container and clean local staging."""
        spec = self._replicas.get(replica_id)
        if not spec:
            return False

        if spec.container_id and self._runtime_available:
            try:
                self._run_cmd([self.container_runtime, "stop", spec.container_id], timeout=30)
                self._run_cmd([self.container_runtime, "rm", "-f", spec.container_id], timeout=30)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Failed to stop replica %s: %s", replica_id[:8], exc)
                return False

        spec.status = NodeStatus.OFFLINE
        work_dir = self._replica_workdirs.pop(replica_id, "")
        if work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)
        logger.info("Replica %s stopped", replica_id[:8])
        return True

    def stop_all(self) -> int:
        """Stop all replicas and return number successfully stopped."""
        count = 0
        for replica_id in list(self._replicas):
            if self.stop_replica(replica_id):
                count += 1
        return count

    # Introspection -----------------------------------------------------

    def list_replicas(self) -> List[ReplicaSpec]:
        return list(self._replicas.values())

    def health_check(self) -> Dict[str, Any]:
        active = sum(1 for spec in self._replicas.values() if spec.status == NodeStatus.ONLINE)
        return {
            "total_replicas": len(self._replicas),
            "active_replicas": active,
            "max_replicas": self.max_replicas,
            "runtime": self.container_runtime,
            "runtime_available": self._runtime_available,
        }

    @staticmethod
    def _validate_env_vars(env_vars: Optional[Dict[str, str]]) -> None:
        if env_vars is None:
            return
        if not isinstance(env_vars, dict):
            raise ValueError("env_vars must be a dictionary")
        for key, value in env_vars.items():
            if not isinstance(key, str) or not _ENV_KEY_PATTERN.match(key):
                raise ValueError(f"invalid environment variable name: {key}")
            if not isinstance(value, str):
                raise ValueError(f"environment variable '{key}' value must be a string")

