"""Top-level trainer orchestrator for cloud CPU continuous adaptation.

Military/tactical context:
This service keeps adaptation loops alive during long-running operations by
combining checkpoint resilience, promotion gates, and resource throttling so
training never destabilizes mission-facing CPU workloads.
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

try:  # Optional runtime dependency for resource checks.
    import psutil
except Exception:  # pragma: no cover - optional runtime
    psutil = None  # type: ignore[assignment]

try:  # Prefer concrete implementations from Chunks 1-3 when available.
    from src.training.cloud_cpu.contracts import CheckpointMeta, TrainerState
    from src.training.cloud_cpu.dataset_cursor import DatasetCursor
    from src.training.cloud_cpu.metrics_store import MetricsStore
    from src.training.cloud_cpu.paths import StatePaths, TrainingTrack
    from src.training.cloud_cpu.promotion_gate import PromotionGate
    from src.training.cloud_cpu.resource_guard import ResourceGuard, ThrottleAction
    from src.training.cloud_cpu.resume_manager import ResumeManager
    from src.training.cloud_cpu.track_router import TrackRouter
    from src.training.cloud_cpu.training_loop import TrainingLoop, StubTrainingBackend
except Exception:  # pragma: no cover - fallback for partially integrated branches
    import yaml

    class TrainingTrack(str, Enum):
        SAUDI_MOD = "saudi_mod"
        UKRAINE_MOD = "ukraine_mod"
        NATO = "nato"
        INDOPAC_MOD = "indopac_mod"
        SOUTHAM_MOD = "southam_mod"
        AFRICA_MOD = "africa_mod"

    @dataclass
    class TrackPaths:
        track: TrainingTrack
        root: Path
        inbox: Path
        runs: Path
        promoted: Path

        def ensure_dirs(self) -> None:
            for directory in (self.root, self.inbox, self.runs, self.promoted):
                directory.mkdir(parents=True, exist_ok=True)

    class StatePaths:
        def __init__(self, root: str | Path = "state/training/cloud_cpu") -> None:
            self.root = Path(root)
            self.locks = self.root / "locks"
            self.metrics = self.root / "metrics"
            self.inbox = self.root / "inbox"
            self.tracks = self.root / "tracks"

        def ensure_dirs(self) -> None:
            for directory in (self.root, self.locks, self.metrics, self.inbox, self.tracks):
                directory.mkdir(parents=True, exist_ok=True)
            for track in TrainingTrack:
                self.for_track(track).ensure_dirs()

        def for_track(self, track: TrainingTrack) -> TrackPaths:
            track_root = self.tracks / track.value
            return TrackPaths(
                track=track,
                root=track_root,
                inbox=self.inbox / track.value,
                runs=track_root / "runs",
                promoted=track_root / "promoted",
            )

    @dataclass
    class CheckpointMeta:
        checkpoint_id: str
        run_id: str
        track: str
        step: int
        epoch: int = 0
        loss: float = 0.0
        is_complete: bool = False
        is_promoted: bool = False
        eval_results: Dict[str, float] = field(default_factory=dict)
        samples_seen: int = 0

        def model_dump(self) -> Dict[str, Any]:
            return asdict(self)

        def model_copy(self, update: Optional[Dict[str, Any]] = None) -> "CheckpointMeta":
            payload = self.model_dump()
            payload.update(update or {})
            return CheckpointMeta(**payload)

    @dataclass
    class TrainerState:
        run_id: str
        current_step: int = 0
        current_epoch: int = 0
        total_samples_processed: int = 0
        heartbeat_at: str = ""
        dataset_cursor: Dict[str, Any] = field(default_factory=dict)
        last_eval: Dict[str, float] = field(default_factory=dict)
        last_promotion: Dict[str, Any] = field(default_factory=dict)

        def model_dump(self) -> Dict[str, Any]:
            return asdict(self)

    class DatasetCursor:
        def __init__(self) -> None:
            self._offset = 0

        def get_cursor(self) -> Dict[str, int]:
            return {"offset": self._offset}

        def restore(self, cursor: Dict[str, Any]) -> None:
            value = cursor.get("offset", 0) if isinstance(cursor, dict) else 0
            self._offset = max(0, int(value))

        def advance(self, count: int) -> None:
            self._offset += max(0, int(count))

    @dataclass
    class CycleMetrics:
        track: str
        step: int
        epoch: int
        loss: float
        samples_processed: int
        timestamp: str

        def model_dump(self) -> Dict[str, Any]:
            return asdict(self)

    class StubTrainingBackend:
        def __init__(self, track: str) -> None:
            self.track = track
            self._weights = {"alpha": 1.0}

        def train_step(self, step: int) -> Dict[str, float]:
            loss = max(0.02, 0.95 * math.exp(-step / 1800.0) + random.gauss(0.0, 0.015))
            return {"loss": float(loss), "samples_processed": float(random.randint(16, 96))}

        def get_state_dict(self) -> Dict[str, Any]:
            return {"track": self.track, "weights": self._weights}

    class TrainingLoop:
        def __init__(
            self,
            track: TrainingTrack,
            config_path: Path,
            state_paths: StatePaths,
            backend: Optional[Any] = None,
        ) -> None:
            self.track = track
            self.config_path = config_path
            self.state_paths = state_paths
            self.backend = backend or StubTrainingBackend(track=track.value)
            self.cursor = DatasetCursor()
            self.step = 0
            self.epoch = 0
            self.config = self._load_config(config_path)

        @staticmethod
        def _load_config(config_path: Path) -> Dict[str, Any]:
            default = {
                "training": {
                    "checkpoint_every_n_steps": 50,
                    "eval_every_n_steps": 200,
                    "idle_sleep_seconds": 10,
                    "cycle_sleep_seconds": 2,
                }
            }
            if not config_path.exists():
                return default
            try:
                data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            except Exception:
                return default
            if not isinstance(data, dict):
                return default
            merged = default.copy()
            merged_training = dict(default.get("training", {}))
            merged_training.update(data.get("training", {}) if isinstance(data.get("training"), dict) else {})
            merged["training"] = merged_training
            return merged

        def run_cycle(self) -> CycleMetrics:
            self.step += 1
            if self.step % 100 == 0:
                self.epoch += 1

            result = self.backend.train_step(self.step)
            samples = max(0, int(result.get("samples_processed", 0)))
            self.cursor.advance(samples)
            return CycleMetrics(
                track=self.track.value,
                step=self.step,
                epoch=self.epoch,
                loss=float(result.get("loss", 0.0)),
                samples_processed=samples,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        def restore(self, step: int, epoch: int, cursor: Dict[str, Any]) -> None:
            self.step = max(0, int(step))
            self.epoch = max(0, int(epoch))
            self.cursor.restore(cursor if isinstance(cursor, dict) else {})

    class TrackRouter:
        def __init__(self, state_paths: StatePaths) -> None:
            self._state_paths = state_paths

        def route_inbox(self) -> Dict[str, int]:
            routed: Dict[str, int] = {}
            for track in TrainingTrack:
                track_inbox = self._state_paths.for_track(track).inbox
                track_inbox.mkdir(parents=True, exist_ok=True)
                routed[track.value] = len([p for p in track_inbox.glob("*") if p.is_file()])
            return routed

    class ResumeManager:
        def __init__(self, state_paths: StatePaths) -> None:
            self._state_paths = state_paths

        def scan_for_resume(self, track: TrainingTrack) -> Optional[CheckpointMeta]:
            paths = self._state_paths.for_track(track)
            candidates: list[CheckpointMeta] = []
            for root in (paths.promoted, paths.runs):
                if not root.exists():
                    continue
                for checkpoint_dir in root.glob("checkpoint-*"):
                    manifest_path = checkpoint_dir / "manifest.json"
                    if not manifest_path.exists():
                        continue
                    try:
                        data = json.loads(manifest_path.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    if not isinstance(data, dict) or not bool(data.get("is_complete", False)):
                        continue
                    try:
                        candidates.append(
                            CheckpointMeta(
                                checkpoint_id=str(data.get("checkpoint_id", checkpoint_dir.name)),
                                run_id=str(data.get("run_id", "")),
                                track=str(data.get("track", track.value)),
                                step=int(data.get("step", 0)),
                                epoch=int(data.get("epoch", 0)),
                                loss=float(data.get("loss", 0.0)),
                                is_complete=True,
                                is_promoted=bool(data.get("is_promoted", root == paths.promoted)),
                                eval_results=(
                                    data.get("eval_results", {})
                                    if isinstance(data.get("eval_results"), dict)
                                    else {}
                                ),
                                samples_seen=int(data.get("samples_seen", 0)),
                            )
                        )
                    except Exception:
                        continue
            if not candidates:
                return None
            return sorted(candidates, key=lambda item: (int(item.is_promoted), item.step), reverse=True)[0]

        def restore_state(self, checkpoint_dir: Path) -> TrainerState:
            state_path = checkpoint_dir / "trainer_state.json"
            if not state_path.exists():
                return TrainerState(run_id="")
            data = json.loads(state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return TrainerState(run_id="")
            return TrainerState(
                run_id=str(data.get("run_id", "")),
                current_step=int(data.get("current_step", 0)),
                current_epoch=int(data.get("current_epoch", 0)),
                total_samples_processed=int(data.get("total_samples_processed", 0)),
                heartbeat_at=str(data.get("heartbeat_at", "")),
                dataset_cursor=data.get("dataset_cursor", {}) if isinstance(data.get("dataset_cursor"), dict) else {},
                last_eval=data.get("last_eval", {}) if isinstance(data.get("last_eval"), dict) else {},
                last_promotion=(
                    data.get("last_promotion", {}) if isinstance(data.get("last_promotion"), dict) else {}
                ),
            )

    class ThrottleAction(str, Enum):
        NONE = "none"
        EVAL_ONLY = "eval_only"
        PAUSE = "pause"

    @dataclass
    class GuardStatus:
        cpu_percent: float
        memory_percent: float
        recommended_action: ThrottleAction

    class ResourceGuard:
        def __init__(self, cpu_eval_only: float = 80.0, cpu_pause: float = 92.0) -> None:
            self.cpu_eval_only = float(cpu_eval_only)
            self.cpu_pause = float(cpu_pause)

        def check(self) -> GuardStatus:
            if psutil is not None:
                cpu = float(psutil.cpu_percent(interval=0.0))
                memory = float(psutil.virtual_memory().percent)
            else:
                load = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
                cores = max(1, os.cpu_count() or 1)
                cpu = float(min(100.0, (load / cores) * 100.0))
                memory = 0.0

            if cpu >= self.cpu_pause or memory >= 92.0:
                action = ThrottleAction.PAUSE
            elif cpu >= self.cpu_eval_only or memory >= 85.0:
                action = ThrottleAction.EVAL_ONLY
            else:
                action = ThrottleAction.NONE
            return GuardStatus(cpu_percent=cpu, memory_percent=memory, recommended_action=action)

    @dataclass
    class PromotionDecision:
        passed: bool
        reason: str
        score_delta: float = 0.0

        def model_dump(self) -> Dict[str, Any]:
            return asdict(self)

    class PromotionGate:
        def __init__(self, global_config_path: Path, track_config_path: Path) -> None:
            self.global_config_path = global_config_path
            self.track_config_path = track_config_path

        def evaluate(
            self,
            meta: CheckpointMeta,
            eval_results: Dict[str, float],
            last_promoted_results: Optional[Dict[str, float]],
            last_promoted_step: int,
        ) -> PromotionDecision:
            overall = float(eval_results.get("overall", 0.0))
            if last_promoted_results:
                previous = float(last_promoted_results.get("overall", 0.0))
                delta = overall - previous
                if delta < 0.01:
                    return PromotionDecision(
                        passed=False,
                        reason=f"overall improvement {delta:.4f} below minimum delta 0.01",
                        score_delta=delta,
                    )
                return PromotionDecision(passed=True, reason="overall improved", score_delta=delta)
            if overall < 0.65:
                return PromotionDecision(passed=False, reason="overall score below initial gate", score_delta=overall)
            return PromotionDecision(passed=True, reason="initial promotion accepted", score_delta=overall)

    class MetricsStore:
        def __init__(self, metrics_root: Path) -> None:
            self._metrics_root = Path(metrics_root)
            self._cycles_file = self._metrics_root / "cycles.jsonl"
            self._promotion_file = self._metrics_root / "promotions.jsonl"
            self._metrics_root.mkdir(parents=True, exist_ok=True)

        def write_cycle(self, metrics: Any) -> None:
            payload = metrics.model_dump() if hasattr(metrics, "model_dump") else dict(metrics)
            self._append_jsonl(self._cycles_file, payload)

        def write_promotion(self, decision: Any) -> None:
            payload = decision.model_dump() if hasattr(decision, "model_dump") else dict(decision)
            payload["timestamp"] = datetime.now(timezone.utc).isoformat()
            self._append_jsonl(self._promotion_file, payload)

        def get_track_summary(self, track: str) -> Dict[str, Any]:
            last: Dict[str, Any] = {}
            count = 0
            if self._cycles_file.exists():
                for line in self._cycles_file.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    if row.get("track") == track:
                        last = row
                        count += 1
            return {"track": track, "cycles": count, "last_cycle": last}

        def get_demo_kpis(self, track: str) -> Dict[str, Any]:
            summary = self.get_track_summary(track)
            last = summary.get("last_cycle", {}) if isinstance(summary.get("last_cycle"), dict) else {}
            return {
                "track": track,
                "step": int(last.get("step", 0)),
                "loss": float(last.get("loss", 0.0)),
                "samples_processed": int(last.get("samples_processed", 0)),
            }

        @staticmethod
        def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, default=str))
                handle.write("\n")

from src.training.cloud_cpu.job_scheduler import JobScheduler

logger = logging.getLogger("s3m.training.trainer_service")


class TrainerService:
    """Orchestrates continuous training lifecycle for a single track."""

    def __init__(self, track: TrainingTrack, paths: StatePaths, backend: Any = None) -> None:
        self._track = track
        self._paths = paths
        self._run_id = f"run-{uuid.uuid4().hex[:12]}"
        self._loop = TrainingLoop(
            track=track,
            config_path=Path(f"configs/training/{track.value}.yaml"),
            state_paths=paths,
            backend=backend or StubTrainingBackend(track=track.value),
        )
        self._resume_mgr = ResumeManager(paths)
        self._promotion_gate = PromotionGate(
            config_path=Path("configs/training/promotion_gate.yaml"),
            track_config_path=Path(f"configs/training/{track.value}.yaml"),
        )
        self._metrics = MetricsStore(paths.metrics)
        self._guard = ResourceGuard()
        self._router = TrackRouter(paths)
        self._scheduler = JobScheduler()

        self._state = TrainerState()
        self._running = False
        self._paused = False
        self._last_checkpoint_step = 0
        self._last_eval_step = 0
        self._last_promoted_results: Optional[Dict[str, float]] = None
        self._last_promoted_step = 0
        self._last_resource_status: Dict[str, Any] = {}
        self._lock_fd: Optional[Any] = None

    def start(self) -> None:
        """Main lifecycle loop; runs until stop() is called."""
        if self._running:
            return
        self._paths.ensure_dirs()
        self._running = True
        self._paused = False
        logger.info("TrainerService starting: track=%s run=%s", self._track.value, self._run_id)

        self._acquire_trainer_lock()
        self._try_resume()

        try:
            while self._running:
                if self._paused:
                    self._heartbeat()
                    time.sleep(1.0)
                    continue
                self.run_cycle_once()
        finally:
            self._release_trainer_lock()
            self._running = False
            logger.info("TrainerService stopped: track=%s run=%s", self._track.value, self._run_id)

    def run_cycle_once(self) -> None:
        """Execute one lifecycle cycle."""
        # A) route incoming dataset packs
        routed = self._router.route_inbox()
        if any(int(v) > 0 for v in routed.values()):
            logger.info("Routed inbox packs: %s", routed)

        # B) resource guard and duty-cycle adjustments
        resource_status = self._guard.check()
        self._last_resource_status = {
            "cpu_percent": float(getattr(resource_status, "cpu_percent", 0.0)),
            "memory_percent": float(getattr(resource_status, "memory_percent", 0.0)),
            "recommended_action": str(getattr(resource_status, "recommended_action", "unknown")),
        }
        self._scheduler.apply_throttle_recommendation(getattr(resource_status, "recommended_action", None))

        if getattr(resource_status, "recommended_action", None) == ThrottleAction.PAUSE:
            logger.warning(
                "Resource guard requested PAUSE (cpu=%.1f%% mem=%.1f%%)",
                float(getattr(resource_status, "cpu_percent", 0.0)),
                float(getattr(resource_status, "memory_percent", 0.0)),
            )
            self._heartbeat()
            time.sleep(max(1.0, self._scheduler.sleep_duration()))
            return

        if not self._scheduler.should_train():
            self._heartbeat()
            time.sleep(max(0.5, self._scheduler.sleep_duration()))
            return

        # C) run one training cycle
        metrics = self._loop.run_cycle()
        self._state.current_step = int(metrics.step)
        self._state.current_epoch = int(metrics.epoch)
        self._state.total_samples_processed += int(metrics.samples_processed)
        self._state.dataset_cursor = self._loop.cursor.get_cursor()
        self._heartbeat()

        # D) write cycle metrics (including resource telemetry)
        self._metrics.write_cycle(metrics)

        if int(metrics.samples_processed) <= 0:
            idle_sleep = float(self._loop.config.get("training", {}).get("idle_sleep_seconds", 10))
            time.sleep(max(0.5, idle_sleep))
            return

        # E) checkpoint on policy
        ckpt_interval = int(self._loop.config.get("training", {}).get("checkpoint_every_n_steps", 50))
        if self._state.current_step - self._last_checkpoint_step >= max(1, ckpt_interval):
            self._save_checkpoint()

        # F/G) evaluate and promote on policy
        eval_interval = int(self._loop.config.get("training", {}).get("eval_every_n_steps", 200))
        if self._state.current_step - self._last_eval_step >= max(1, eval_interval):
            self._run_eval_and_maybe_promote()

        # H/I/J/K) telemetry + heartbeat + controlled sleep
        self._heartbeat()
        if self._scheduler.should_sleep():
            time.sleep(max(0.5, self._scheduler.sleep_duration()))
        else:
            cycle_sleep = float(self._loop.config.get("training", {}).get("cycle_sleep_seconds", 2))
            time.sleep(max(0.0, cycle_sleep))

    def pause(self) -> None:
        self._paused = True
        logger.info("Training paused: track=%s", self._track.value)

    def resume(self) -> None:
        self._paused = False
        logger.info("Training resumed: track=%s", self._track.value)

    def stop(self) -> None:
        self._running = False
        logger.info("Training stop requested: track=%s", self._track.value)

    def get_status(self) -> Dict[str, Any]:
        return {
            "track": self._track.value,
            "run_id": self._run_id,
            "running": self._running,
            "paused": self._paused,
            "state": self._state.model_dump(),
            "resource_status": self._last_resource_status,
            "summary": self._metrics.get_track_summary(self._track.value),
            "demo_kpis": self._metrics.get_demo_kpis(self._track.value),
        }

    def _heartbeat(self) -> None:
        self._state.heartbeat_at = datetime.now(timezone.utc).isoformat()

    def _acquire_trainer_lock(self) -> None:
        lock_path = self._paths.locks / f"{self._track.value}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import fcntl

            self._lock_fd = open(lock_path, "w", encoding="utf-8")
            fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_fd.write(f"{os.getpid()}\n")
            self._lock_fd.flush()
        except Exception:
            if self._lock_fd:
                try:
                    self._lock_fd.close()
                except Exception:
                    pass
                self._lock_fd = None
            raise RuntimeError(f"unable to acquire trainer lock: {lock_path}")

    def _release_trainer_lock(self) -> None:
        if not self._lock_fd:
            return
        lock_path = Path(self._lock_fd.name)
        try:
            import fcntl

            fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            self._lock_fd.close()
        finally:
            self._lock_fd = None
        try:
            lock_path.unlink(missing_ok=True)
        except Exception:
            logger.debug("Unable to remove lock file %s", lock_path)

    def _try_resume(self) -> None:
        meta = self._resume_mgr.scan_for_resume(self._track)
        if not meta:
            return
        track_paths = self._paths.for_track(self._track)
        checkpoint_dir = track_paths.runs / meta.checkpoint_id
        if not checkpoint_dir.exists():
            checkpoint_dir = track_paths.promoted / meta.checkpoint_id
        if not checkpoint_dir.exists():
            return

        state = self._resume_mgr.restore_state(checkpoint_dir)
        state.run_id = self._run_id
        self._state = state
        self._loop.restore(
            step=self._state.current_step,
            epoch=self._state.current_epoch,
            cursor=self._state.dataset_cursor,
        )
        self._last_checkpoint_step = self._state.current_step
        self._last_eval_step = self._state.current_step
        if meta.is_promoted and isinstance(meta.eval_results, dict):
            self._last_promoted_results = {
                key: float(value)
                for key, value in meta.eval_results.items()
                if isinstance(value, (int, float))
            }
            self._last_promoted_step = int(meta.step)
        logger.info("Resumed from checkpoint %s at step=%d", meta.checkpoint_id, self._state.current_step)

    def _save_checkpoint(self) -> None:
        step = int(self._loop.step)
        checkpoint_id = f"checkpoint-{step:09d}"
        track_paths = self._paths.for_track(self._track)
        checkpoint_dir = track_paths.runs / checkpoint_id
        tmp_dir = track_paths.runs / f"{checkpoint_id}.tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        metadata = CheckpointMeta(
            checkpoint_id=checkpoint_id,
            run_id=self._run_id,
            track=self._track.value,
            step=step,
            epoch=int(self._loop.epoch),
            loss=0.0,
            is_complete=False,
            samples_seen=int(self._state.total_samples_processed),
        )
        (tmp_dir / "manifest.json").write_text(
            json.dumps(metadata.model_dump(), indent=2, default=str),
            encoding="utf-8",
        )
        (tmp_dir / "trainer_state.json").write_text(
            json.dumps(self._state.model_dump(), indent=2, default=str),
            encoding="utf-8",
        )
        (tmp_dir / "model_state.json").write_text(
            json.dumps(self._loop.backend.get_state_dict(), indent=2, default=str),
            encoding="utf-8",
        )

        if checkpoint_dir.exists():
            shutil.rmtree(checkpoint_dir)
        tmp_dir.rename(checkpoint_dir)

        complete_meta = metadata.model_copy(update={"is_complete": True})
        (checkpoint_dir / "manifest.json").write_text(
            json.dumps(complete_meta.model_dump(), indent=2, default=str),
            encoding="utf-8",
        )
        self._last_checkpoint_step = step
        logger.info("Checkpoint saved: %s", checkpoint_id)

    def _run_eval_and_maybe_promote(self) -> None:
        step = int(self._loop.step)
        eval_results = self._simulate_eval(step)
        self._state.last_eval = eval_results
        self._last_eval_step = step
        logger.info("Eval at step=%d results=%s", step, eval_results)

        meta = CheckpointMeta(
            checkpoint_id=f"checkpoint-{step:09d}",
            run_id=self._run_id,
            track=self._track.value,
            step=step,
            epoch=int(self._loop.epoch),
            eval_results=eval_results,
        )
        decision = self._promotion_gate.evaluate(
            meta=meta,
            eval_results=eval_results,
            last_promoted_results=self._last_promoted_results,
            last_promoted_step=self._last_promoted_step,
        )
        self._metrics.write_promotion(decision)
        if bool(getattr(decision, "passed", False)):
            self._promote_checkpoint(meta=meta, eval_results=eval_results)
        else:
            logger.info("Promotion declined at step=%d reason=%s", step, getattr(decision, "reason", "n/a"))

    def _promote_checkpoint(self, meta: CheckpointMeta, eval_results: Dict[str, float]) -> None:
        source = self._paths.for_track(self._track).runs / meta.checkpoint_id
        destination = self._paths.for_track(self._track).promoted / meta.checkpoint_id
        if not source.exists():
            logger.warning("Cannot promote missing checkpoint: %s", source)
            return
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)

        promoted_meta = meta.model_copy(update={"is_promoted": True, "is_complete": True, "eval_results": eval_results})
        (destination / "manifest.json").write_text(
            json.dumps(promoted_meta.model_dump(), indent=2, default=str),
            encoding="utf-8",
        )

        self._last_promoted_results = eval_results
        self._last_promoted_step = int(meta.step)
        self._state.last_promotion = {
            "checkpoint_id": meta.checkpoint_id,
            "step": int(meta.step),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scores": eval_results,
        }
        logger.info("Promoted checkpoint %s at step=%d", meta.checkpoint_id, meta.step)

    def _simulate_eval(self, step: int) -> Dict[str, float]:
        base = min(0.95, 0.45 + 0.35 * (1 - math.exp(-step / 800.0)))
        if self._track == TrainingTrack.SAUDI_MOD:
            return {
                "arabic_fidelity": round(min(0.98, base * 1.05 + random.gauss(0, 0.02)), 3),
                "structured_output": round(min(0.99, base * 1.10 + random.gauss(0, 0.015)), 3),
                "command_quality": round(min(0.97, base * 1.02 + random.gauss(0, 0.02)), 3),
                "overall": round(min(0.97, base + random.gauss(0, 0.015)), 3),
            }
        if self._track == TrainingTrack.UKRAINE_MOD:
            return {
                "degraded_recovery": round(min(0.95, base * 0.98 + random.gauss(0, 0.025)), 3),
                "adaptation": round(min(0.93, base * 0.95 + random.gauss(0, 0.02)), 3),
                "report_compliance": round(min(0.96, base * 1.05 + random.gauss(0, 0.02)), 3),
                "overall": round(min(0.94, base * 0.99 + random.gauss(0, 0.02)), 3),
            }
        return {
            "format_compliance": round(min(0.98, base * 1.12 + random.gauss(0, 0.015)), 3),
            "doctrinal": round(min(0.96, base * 1.03 + random.gauss(0, 0.02)), 3),
            "stability": round(min(0.97, base * 1.06 + random.gauss(0, 0.015)), 3),
            "overall": round(min(0.96, base * 1.02 + random.gauss(0, 0.015)), 3),
        }

