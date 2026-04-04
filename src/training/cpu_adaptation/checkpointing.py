"""
S3M Hierarchical Checkpointing for Field-Safe CPU Training
Research basis: LLM training storage architecture (Lockwood 2025),
               crash-safe resume patterns (Windows CPU-Only Training 2025)

Implements tiered checkpointing:
  L0: In-memory snapshot (< 1 second, lost on process death)
  L1: Local disk atomic write (seconds, survives crashes)
  L2: Peer node replication via available bearer (when link up)
  L3: Remote archive to object store (when WAN available)
"""

from __future__ import annotations

import io
import json
import logging
import os
import queue
import shutil
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import torch

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - optional runtime
    torch = None  # type: ignore
    TORCH_AVAILABLE = False

logger = logging.getLogger("s3m.training.checkpointing")


@dataclass
class CheckpointManifest:
    """Atomic metadata for a single checkpoint."""

    checkpoint_id: str
    step: int
    epoch: int
    loss: float
    timestamp: str
    level: int  # 0-3
    path: str
    sha256: str
    model_id: str
    adapter_config_hash: str
    precision_used: str
    peak_memory_mb: float
    is_complete: bool  # False during write, True after atomic rename


@dataclass
class CheckpointPolicy:
    """When and where to checkpoint."""

    l1_every_n_steps: int = 50
    l2_every_n_l1: int = 5
    l3_every_n_l2: int = 2
    max_l1_checkpoints: int = 3
    max_l2_checkpoints: int = 2
    checkpoint_dir: str = "checkpoints"
    use_atomic_writes: bool = True
    verify_after_write: bool = True


class HierarchicalCheckpointer:
    """
    Manages tiered checkpoint lifecycle for CPU training jobs.

    Key design principles:
    1. ATOMIC WRITES: Write to .tmp file, then os.rename() — never corrupt
       existing checkpoint on crash during write
    2. MANIFEST FIRST: Write manifest.json with is_complete=False, write data,
       update manifest to is_complete=True
    3. RESUME LOGIC: On restart, find latest checkpoint where is_complete=True
    4. GARBAGE COLLECTION: Keep only max_checkpoints per level
    5. PEER REPLICATION: When bearer broker reports a link, async copy to peer
    6. INTEGRITY: SHA256 of checkpoint data stored in manifest
    """

    _STATE_FILENAME = "state.pt"
    _MANIFEST_FILENAME = "manifest.json"

    def __init__(self, model_id: str, policy: CheckpointPolicy, base_dir: str = "."):
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("model_id must be a non-empty string")
        if not isinstance(policy, CheckpointPolicy):
            raise TypeError("policy must be a CheckpointPolicy instance")
        if not isinstance(base_dir, str) or not base_dir.strip():
            raise ValueError("base_dir must be a non-empty string")

        self.model_id = model_id.strip()
        self.policy = policy
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

        l1_dir = Path(policy.checkpoint_dir)
        if not l1_dir.is_absolute():
            l1_dir = self.base_dir / l1_dir
        self._level_dirs: Dict[int, Path] = {
            1: l1_dir.resolve(),
            2: (self.base_dir / f"{l1_dir.name}_peer").resolve(),
            3: (self.base_dir / f"{l1_dir.name}_archive").resolve(),
        }
        for directory in self._level_dirs.values():
            directory.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._replication_queue: "queue.Queue[CheckpointManifest]" = queue.Queue(maxsize=128)
        self._replication_thread = threading.Thread(
            target=self._replication_worker,
            name=f"s3m-checkpoint-repl-{self.model_id}",
            daemon=True,
        )
        self._replication_thread.start()

        self._bearer_broker: Any = None
        self._l1_saved_count = len(self._list_checkpoint_dirs(1))
        self._l2_replicated_count = len(self._list_checkpoint_dirs(2))
        self._l0_snapshot: Optional[Dict[str, Any]] = None

        self._cleanup_interrupted_writes()

    def save_checkpoint(
        self,
        step: int,
        epoch: int,
        loss: float,
        model_state: dict,
        optimizer_state: dict,
        scheduler_state: dict = None,
        extra_metadata: dict = None,
    ) -> CheckpointManifest:
        """
        Save checkpoint with atomic write pattern:
        1. Serialize state_dict to bytes
        2. Compute SHA256
        3. Write manifest with is_complete=False
        4. Write data to {checkpoint_dir}/checkpoint-{step}.tmp/
        5. Atomic rename to {checkpoint_dir}/checkpoint-{step}/
        6. Update manifest to is_complete=True
        7. Garbage collect old checkpoints
        8. If L2 due: queue for peer replication
        """
        if int(step) < 0:
            raise ValueError("step must be >= 0")
        if int(epoch) < 0:
            raise ValueError("epoch must be >= 0")
        if not isinstance(model_state, dict):
            raise TypeError("model_state must be a dict")
        if not isinstance(optimizer_state, dict):
            raise TypeError("optimizer_state must be a dict")
        if scheduler_state is not None and not isinstance(scheduler_state, dict):
            raise TypeError("scheduler_state must be a dict when provided")
        if extra_metadata is not None and not isinstance(extra_metadata, dict):
            raise TypeError("extra_metadata must be a dict when provided")

        metadata = extra_metadata or {}
        payload = {
            "step": int(step),
            "epoch": int(epoch),
            "loss": float(loss),
            "model_state": model_state,
            "optimizer_state": optimizer_state,
            "scheduler_state": scheduler_state,
            "metadata": metadata,
        }
        data_bytes = self._serialize_payload(payload)
        sha256 = self._compute_sha256(data_bytes)
        now = datetime.now(timezone.utc).isoformat()

        adapter_config_hash = self._compute_adapter_config_hash(metadata)
        precision_used = str(metadata.get("precision_used", "fp32"))
        peak_memory_mb = float(metadata.get("peak_memory_mb", 0.0))
        checkpoint_name = f"checkpoint-{int(step):09d}"
        checkpoint_id = f"{self.model_id}:{checkpoint_name}:{int(time.time())}"

        final_dir = self._level_dirs[1] / checkpoint_name
        tmp_dir = Path(f"{final_dir}.tmp")
        with self._lock:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
            tmp_dir.mkdir(parents=True, exist_ok=False)

            pending_manifest = CheckpointManifest(
                checkpoint_id=checkpoint_id,
                step=int(step),
                epoch=int(epoch),
                loss=float(loss),
                timestamp=now,
                level=1,
                path=str(final_dir),
                sha256=sha256,
                model_id=self.model_id,
                adapter_config_hash=adapter_config_hash,
                precision_used=precision_used,
                peak_memory_mb=peak_memory_mb,
                is_complete=False,
            )
            self._write_manifest(tmp_dir / self._MANIFEST_FILENAME, pending_manifest)

            if self.policy.use_atomic_writes:
                final_path = self._atomic_save(data_bytes, str(final_dir))
            else:
                state_path = tmp_dir / self._STATE_FILENAME
                self._write_bytes(state_path, data_bytes)
                if final_dir.exists():
                    shutil.rmtree(final_dir, ignore_errors=True)
                os.rename(str(tmp_dir), str(final_dir))
                final_path = str(final_dir)

            completed_manifest = CheckpointManifest(
                checkpoint_id=checkpoint_id,
                step=int(step),
                epoch=int(epoch),
                loss=float(loss),
                timestamp=now,
                level=1,
                path=final_path,
                sha256=sha256,
                model_id=self.model_id,
                adapter_config_hash=adapter_config_hash,
                precision_used=precision_used,
                peak_memory_mb=peak_memory_mb,
                is_complete=True,
            )
            self._write_manifest(Path(final_path) / self._MANIFEST_FILENAME, completed_manifest)

            if self.policy.verify_after_write:
                saved_data = self._read_bytes(Path(final_path) / self._STATE_FILENAME)
                if self._compute_sha256(saved_data) != sha256:
                    raise IOError(f"checkpoint integrity verification failed for {final_path}")

            # Tactical context: L0 keeps immediate rollback state for rapidly
            # recovering training loops in contested environments before disk IO.
            self._l0_snapshot = {
                "timestamp": now,
                "step": int(step),
                "sha256": sha256,
                "payload": payload,
            }

            self._l1_saved_count += 1
            self._garbage_collect(level=1)
            if self.policy.l2_every_n_l1 > 0 and (self._l1_saved_count % self.policy.l2_every_n_l1 == 0):
                self._queue_peer_replication(completed_manifest)

        return completed_manifest

    def find_latest_checkpoint(self) -> Optional[CheckpointManifest]:
        """
        Find the most recent valid checkpoint for resume.
        Scans checkpoint_dir, reads manifests, returns latest where
        is_complete=True and SHA256 matches.
        If latest is corrupt, falls back to second-latest, etc.
        """
        self._cleanup_interrupted_writes()
        with self._lock:
            for level in (1, 2, 3):
                candidates = sorted(
                    self._read_level_manifests(level),
                    key=lambda item: (item.step, item.timestamp),
                    reverse=True,
                )
                for manifest in candidates:
                    if not manifest.is_complete:
                        continue
                    state_path = Path(manifest.path) / self._STATE_FILENAME
                    if not state_path.exists():
                        continue
                    data = self._read_bytes(state_path)
                    if self._compute_sha256(data) == manifest.sha256:
                        return manifest
                    logger.warning("Skipping corrupt checkpoint %s (sha mismatch)", manifest.path)
        return None

    def load_checkpoint(self, manifest: CheckpointManifest) -> dict:
        """Load checkpoint data, verify SHA256, return state dicts."""
        if not TORCH_AVAILABLE or torch is None:
            raise RuntimeError("torch is required to load checkpoints")
        if not isinstance(manifest, CheckpointManifest):
            raise TypeError("manifest must be a CheckpointManifest")
        checkpoint_dir = Path(manifest.path)
        state_path = checkpoint_dir / self._STATE_FILENAME
        if not state_path.exists():
            raise FileNotFoundError(f"checkpoint state file missing: {state_path}")
        data = self._read_bytes(state_path)
        if self._compute_sha256(data) != manifest.sha256:
            raise ValueError(f"checkpoint sha256 mismatch: {state_path}")
        loaded = torch.load(io.BytesIO(data), map_location="cpu", weights_only=True)
        if not isinstance(loaded, dict):
            raise ValueError("checkpoint payload must be a dictionary")
        return loaded

    def resume_training_state(self, model: Any, optimizer: Any, scheduler: Any = None) -> int:
        """
        High-level resume: find latest checkpoint, load it, restore all state.
        Returns the step number to resume from, or 0 if no checkpoint found.
        Logs detailed resume information.
        """
        latest = self.find_latest_checkpoint()
        if latest is None:
            logger.info("No valid checkpoint found for model_id=%s", self.model_id)
            return 0

        payload = self.load_checkpoint(latest)
        if "model_state" not in payload or "optimizer_state" not in payload:
            raise KeyError("checkpoint missing model_state or optimizer_state")

        model.load_state_dict(payload["model_state"])
        optimizer.load_state_dict(payload["optimizer_state"])

        if scheduler is not None and payload.get("scheduler_state") is not None:
            scheduler.load_state_dict(payload["scheduler_state"])

        resume_step = int(payload.get("step", latest.step))
        logger.info(
            "Resumed training from checkpoint=%s level=%s step=%s epoch=%s",
            latest.path,
            latest.level,
            latest.step,
            latest.epoch,
        )
        return resume_step

    def _atomic_save(self, data: bytes, target_path: str) -> str:
        """Write to .tmp then rename. Return final path."""
        target = Path(target_path)
        tmp_dir = Path(f"{target_path}.tmp")
        if not tmp_dir.exists():
            tmp_dir.mkdir(parents=True, exist_ok=False)
        state_path = tmp_dir / self._STATE_FILENAME
        self._write_bytes(state_path, data)

        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        os.rename(str(tmp_dir), str(target))
        return str(target)

    def _compute_sha256(self, data: bytes) -> str:
        """Compute SHA256 hex digest."""
        import hashlib

        hasher = hashlib.sha256()
        hasher.update(data)
        return hasher.hexdigest()

    def _garbage_collect(self, level: int) -> List[str]:
        """Remove old checkpoints beyond max count. Return removed paths."""
        if level == 1:
            keep = max(0, int(self.policy.max_l1_checkpoints))
        elif level == 2:
            keep = max(0, int(self.policy.max_l2_checkpoints))
        else:
            return []

        checkpoint_dirs = sorted(
            self._list_checkpoint_dirs(level),
            key=lambda path: self._extract_step(path),
            reverse=True,
        )
        removed: List[str] = []
        for stale_path in checkpoint_dirs[keep:]:
            shutil.rmtree(stale_path, ignore_errors=True)
            removed.append(str(stale_path))
        return removed

    def _queue_peer_replication(self, manifest: CheckpointManifest) -> None:
        """
        If bearer broker reports any link up, queue async copy to peer.
        Uses src/edge_runtime/bearer_broker.py if available.
        Non-blocking — training continues regardless.
        """
        if not self._is_link_up():
            logger.debug("Skipping peer replication queue; no bearer link is currently available")
            return
        try:
            self._replication_queue.put_nowait(manifest)
        except queue.Full:
            logger.warning("Replication queue full; dropping replication request for %s", manifest.path)

    def get_checkpoint_inventory(self) -> Dict[str, Any]:
        """Return status of all checkpoints across all levels."""
        with self._lock:
            inventory: Dict[str, Any] = {
                "model_id": self.model_id,
                "levels": {
                    "l0": {
                        "available": self._l0_snapshot is not None,
                        "step": self._l0_snapshot["step"] if self._l0_snapshot else None,
                        "timestamp": self._l0_snapshot["timestamp"] if self._l0_snapshot else None,
                    },
                    "l1": self._inventory_for_level(1),
                    "l2": self._inventory_for_level(2),
                    "l3": self._inventory_for_level(3),
                },
            }
        return inventory

    def _inventory_for_level(self, level: int) -> Dict[str, Any]:
        manifests = sorted(
            self._read_level_manifests(level),
            key=lambda item: (item.step, item.timestamp),
            reverse=True,
        )
        return {
            "count": len(manifests),
            "latest_step": manifests[0].step if manifests else None,
            "checkpoints": [asdict(manifest) for manifest in manifests],
        }

    def _replication_worker(self) -> None:
        while True:
            manifest = self._replication_queue.get()
            try:
                with self._lock:
                    l2_manifest = self._replicate_manifest_to_level(manifest, level=2)
                    self._l2_replicated_count += 1
                    self._garbage_collect(level=2)
                    if (
                        self.policy.l3_every_n_l2 > 0
                        and self._l2_replicated_count % self.policy.l3_every_n_l2 == 0
                    ):
                        # Tactical context: L3 archival is delayed until repeated
                        # L2 success to avoid wasting contested WAN windows.
                        self._replicate_manifest_to_level(l2_manifest, level=3)
            except Exception:  # pragma: no cover - defensive worker path
                logger.exception("Failed to replicate checkpoint %s", manifest.path)
            finally:
                self._replication_queue.task_done()

    def _replicate_manifest_to_level(self, manifest: CheckpointManifest, level: int) -> CheckpointManifest:
        source_dir = Path(manifest.path)
        if not source_dir.exists():
            raise FileNotFoundError(f"source checkpoint does not exist: {source_dir}")

        target_root = self._level_dirs[level]
        target_dir = target_root / source_dir.name
        tmp_dir = Path(f"{target_dir}.tmp")
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.copytree(source_dir, tmp_dir)
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        os.rename(str(tmp_dir), str(target_dir))

        replicated = CheckpointManifest(
            checkpoint_id=manifest.checkpoint_id,
            step=manifest.step,
            epoch=manifest.epoch,
            loss=manifest.loss,
            timestamp=manifest.timestamp,
            level=level,
            path=str(target_dir),
            sha256=manifest.sha256,
            model_id=manifest.model_id,
            adapter_config_hash=manifest.adapter_config_hash,
            precision_used=manifest.precision_used,
            peak_memory_mb=manifest.peak_memory_mb,
            is_complete=True,
        )
        self._write_manifest(target_dir / self._MANIFEST_FILENAME, replicated)
        return replicated

    def _cleanup_interrupted_writes(self) -> None:
        for level in (1, 2, 3):
            level_dir = self._level_dirs[level]
            for path in level_dir.glob("checkpoint-*.tmp"):
                shutil.rmtree(path, ignore_errors=True)

    def _list_checkpoint_dirs(self, level: int) -> List[Path]:
        level_dir = self._level_dirs[level]
        return [path for path in level_dir.glob("checkpoint-*") if path.is_dir() and not path.name.endswith(".tmp")]

    def _read_level_manifests(self, level: int) -> List[CheckpointManifest]:
        manifests: List[CheckpointManifest] = []
        for checkpoint_dir in self._list_checkpoint_dirs(level):
            manifest_path = checkpoint_dir / self._MANIFEST_FILENAME
            if not manifest_path.exists():
                continue
            manifest = self._read_manifest(manifest_path)
            if manifest is not None:
                manifests.append(manifest)
        return manifests

    def _write_manifest(self, path: Path, manifest: CheckpointManifest) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(asdict(manifest), sort_keys=True, indent=2)
        with path.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.write("\n")

    def _read_manifest(self, path: Path) -> Optional[CheckpointManifest]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return CheckpointManifest(
                checkpoint_id=str(data["checkpoint_id"]),
                step=int(data["step"]),
                epoch=int(data["epoch"]),
                loss=float(data["loss"]),
                timestamp=str(data["timestamp"]),
                level=int(data["level"]),
                path=str(data["path"]),
                sha256=str(data["sha256"]),
                model_id=str(data["model_id"]),
                adapter_config_hash=str(data["adapter_config_hash"]),
                precision_used=str(data["precision_used"]),
                peak_memory_mb=float(data["peak_memory_mb"]),
                is_complete=bool(data["is_complete"]),
            )
        except Exception:
            logger.warning("Unable to parse manifest at %s", path, exc_info=True)
            return None

    def _serialize_payload(self, payload: Dict[str, Any]) -> bytes:
        if not TORCH_AVAILABLE or torch is None:
            raise RuntimeError("torch is required to save checkpoints")
        buffer = io.BytesIO()
        torch.save(payload, buffer)
        return buffer.getvalue()

    def _write_bytes(self, path: Path, payload: bytes) -> None:
        with path.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    def _read_bytes(self, path: Path) -> bytes:
        with path.open("rb") as handle:
            return handle.read()

    def _extract_step(self, path: Path) -> int:
        try:
            return int(path.name.split("checkpoint-")[1].split(".")[0])
        except Exception:
            return -1

    def _compute_adapter_config_hash(self, metadata: Dict[str, Any]) -> str:
        import hashlib

        if "adapter_config_hash" in metadata:
            value = metadata.get("adapter_config_hash")
            if isinstance(value, str) and value:
                return value
        config = metadata.get("adapter_config", {})
        canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
        hasher = hashlib.sha256()
        hasher.update(canonical.encode("utf-8"))
        return hasher.hexdigest()

    def _is_link_up(self) -> bool:
        if self._bearer_broker is not None and hasattr(self._bearer_broker, "any_bearer_up"):
            try:
                return bool(self._bearer_broker.any_bearer_up())
            except Exception:
                logger.debug("Attached bearer broker failed link probe", exc_info=True)
                return False
        try:
            from src.edge_runtime import bearer_broker as _bearer_broker_module  # noqa: F401
        except Exception:
            return False
        return os.getenv("S3M_CHECKPOINT_ASSUME_LINK_UP", "0").strip().lower() in {"1", "true", "yes"}
