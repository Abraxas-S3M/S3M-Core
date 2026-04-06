"""Resume ladder for cloud CPU training.

Military/tactical context:
Resume prioritizes mission-qualified checkpoints (promoted) before opportunistic
local run checkpoints, then shared fallback, to preserve doctrine fidelity when
nodes restart under degraded conditions.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Dict, Optional

from src.training.cloud_cpu.contracts import CheckpointMeta, TrainerState
from src.training.cloud_cpu.paths import StatePaths, TrainingTrack
from src.training.cpu_adaptation.checkpointing import CheckpointPolicy, HierarchicalCheckpointer

logger = logging.getLogger("s3m.training.cloud_cpu.resume_manager")


class ResumeManager:
    """Finds and restores best-available checkpoints using a fixed ladder."""

    def __init__(self, paths: StatePaths) -> None:
        self._paths = paths
        self._probes: Dict[str, HierarchicalCheckpointer] = {}
        self._cleanup_orphans()

    def scan_for_resume(self, track: TrainingTrack) -> Optional[CheckpointMeta]:
        """Return best verified checkpoint using:
        promoted -> latest complete run -> shared promoted -> cold start.
        """
        if not isinstance(track, TrainingTrack):
            track = TrainingTrack(str(track))
        track_paths = self._paths.for_track(track)

        candidate = self._latest_verified(track_paths.promoted, f"{track.value}-promoted", "promoted")
        if candidate is not None:
            return candidate

        candidate = self._latest_verified(track_paths.runs, f"{track.value}-runs", "latest")
        if candidate is not None:
            return candidate

        shared_promoted = self._paths.for_track(TrainingTrack.SHARED).promoted
        candidate = self._latest_verified(shared_promoted, "shared-promoted", "shared")
        if candidate is not None:
            return candidate

        return None

    def restore_state(self, checkpoint_meta: CheckpointMeta) -> TrainerState:
        """Load TrainerState from a verified checkpoint directory."""
        if not isinstance(checkpoint_meta, CheckpointMeta):
            raise TypeError("checkpoint_meta must be a CheckpointMeta instance")

        checkpoint_dir = Path(checkpoint_meta.path)
        self._verify_sha(checkpoint_dir, expected_sha256=checkpoint_meta.sha256)

        trainer_state_path = checkpoint_dir / "trainer_state.json"
        if trainer_state_path.exists():
            payload = json.loads(trainer_state_path.read_text(encoding="utf-8"))
            state = TrainerState.from_dict(payload)
        else:
            state = TrainerState(
                step=int(checkpoint_meta.step),
                epoch=int(checkpoint_meta.epoch),
                last_loss=float(checkpoint_meta.loss),
                metadata={"restore_without_trainer_state": True},
            )
        state.resume_count += 1
        if state.step < checkpoint_meta.step:
            state.step = int(checkpoint_meta.step)
        if state.epoch < checkpoint_meta.epoch:
            state.epoch = int(checkpoint_meta.epoch)
        return state

    def _latest_verified(
        self,
        checkpoint_root: Path,
        probe_model_id: str,
        source: str,
    ) -> Optional[CheckpointMeta]:
        if not checkpoint_root.exists():
            return None

        checkpointer = self._probe_for(checkpoint_root=checkpoint_root, probe_model_id=probe_model_id)
        manifest = checkpointer.find_latest_checkpoint()
        if manifest is None:
            return None

        checkpoint_dir = Path(manifest.path).resolve()
        if checkpoint_dir.parent != checkpoint_root.resolve():
            logger.warning("Ignoring checkpoint outside probe root: %s", checkpoint_dir)
            return None

        return CheckpointMeta(
            checkpoint_id=str(manifest.checkpoint_id),
            step=int(manifest.step),
            epoch=int(manifest.epoch),
            loss=float(manifest.loss),
            timestamp=str(manifest.timestamp),
            level=int(manifest.level),
            path=str(manifest.path),
            sha256=str(manifest.sha256),
            model_id=str(manifest.model_id),
            adapter_config_hash=str(manifest.adapter_config_hash),
            precision_used=str(manifest.precision_used),
            peak_memory_mb=float(manifest.peak_memory_mb),
            is_complete=bool(manifest.is_complete),
            source=source,
        )

    def _probe_for(self, checkpoint_root: Path, probe_model_id: str) -> HierarchicalCheckpointer:
        key = str(checkpoint_root.resolve())
        cached = self._probes.get(key)
        if cached is not None:
            return cached

        policy = CheckpointPolicy(
            checkpoint_dir=str(checkpoint_root),
            l2_every_n_l1=1_000_000,
            l3_every_n_l2=1_000_000,
            max_l1_checkpoints=10_000,
            max_l2_checkpoints=10_000,
            verify_after_write=True,
        )
        probe = HierarchicalCheckpointer(
            model_id=probe_model_id,
            policy=policy,
            base_dir=str(checkpoint_root.parent),
        )
        self._probes[key] = probe
        return probe

    def _verify_sha(self, checkpoint_dir: Path, expected_sha256: str) -> None:
        state_file = checkpoint_dir / "state.pt"
        manifest_file = checkpoint_dir / "manifest.json"
        if not manifest_file.exists():
            raise FileNotFoundError(f"missing manifest for checkpoint: {manifest_file}")
        if not state_file.exists():
            raise FileNotFoundError(f"missing state payload for checkpoint: {state_file}")

        manifest_payload = json.loads(manifest_file.read_text(encoding="utf-8"))
        if not bool(manifest_payload.get("is_complete", False)):
            raise ValueError(f"checkpoint is incomplete: {checkpoint_dir}")
        manifest_sha = str(manifest_payload.get("sha256", "")).strip().lower()
        if manifest_sha != str(expected_sha256).strip().lower():
            raise ValueError(f"checkpoint manifest sha mismatch at {checkpoint_dir}")

        hasher = hashlib.sha256()
        with state_file.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(block)
        digest = hasher.hexdigest().lower()
        if digest != manifest_sha:
            raise ValueError(f"checkpoint payload sha mismatch at {checkpoint_dir}")

    def _cleanup_orphans(self) -> None:
        """Remove interrupted .tmp directories left by failed writes."""
        for track in TrainingTrack:
            track_paths = self._paths.for_track(track)
            for parent in (track_paths.runs, track_paths.promoted):
                if not parent.exists():
                    continue
                for path in parent.iterdir():
                    if not path.name.endswith(".tmp"):
                        continue
                    try:
                        if path.is_dir():
                            shutil.rmtree(path, ignore_errors=True)
                        else:
                            path.unlink(missing_ok=True)
                    except OSError:
                        logger.warning("Unable to cleanup orphan temp path: %s", path)

