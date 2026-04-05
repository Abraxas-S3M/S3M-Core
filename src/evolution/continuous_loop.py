"""
S3M Continuous Evolution Loop — closed-loop self-improvement.

Military/tactical context:
This loop captures operational outcomes and continuously updates models while
enforcing version-gated promotion and rollback to avoid degraded deployments.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .experience_replay import Experience, PrioritizedReplayBuffer
from .model_versioner import ModelVersioner

logger = logging.getLogger(__name__)


class EvolutionConfig(BaseModel):
    """Configuration for continuous learning and promotion cycles."""

    retrain_interval_samples: int = Field(default=100, ge=10, le=100000)
    evaluation_window: int = Field(default=50, ge=10, le=10000)
    replay_batch_size: int = Field(default=32, ge=4, le=8192)
    auto_promote: bool = True
    max_replay_buffer: int = Field(default=50000, ge=100, le=500000)
    regression_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    checkpoint_dir: str = Field(default="checkpoints/evolution", min_length=1)
    checkpoint_every_cycles: int = Field(default=1, ge=1, le=1000)


class EvolutionCycle(BaseModel):
    """Audit record for one retrain/evaluate/promote cycle."""

    cycle_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    samples_since_last_retrain: int = 0
    retrain_triggered: bool = False
    model_promoted: bool = False
    regression_detected: bool = False
    metrics: Dict[str, float] = Field(default_factory=dict)


class ContinuousEvolutionLoop:
    """Thread-safe orchestrator for online replay/retrain/promotion."""

    def __init__(
        self,
        learner: Optional[Any] = None,
        config: Optional[EvolutionConfig] = None,
        model_name: str = "s3m_online",
    ) -> None:
        self.config = config or EvolutionConfig()
        self._learner = learner
        self._replay = PrioritizedReplayBuffer(capacity=self.config.max_replay_buffer)
        self._versioner = ModelVersioner(
            model_name=model_name,
            regression_threshold=self.config.regression_threshold,
        )
        self._samples_since_retrain = 0
        self._total_samples = 0
        self._cycles: List[EvolutionCycle] = []
        self._lock = threading.RLock()
        self._cycle_lock = threading.Lock()

    def ingest(self, experience: Experience) -> Optional[EvolutionCycle]:
        if not isinstance(experience, Experience):
            raise TypeError("experience must be an Experience instance")

        self._replay.add(experience)
        if self._learner is not None and hasattr(self._learner, "learn"):
            try:
                self._learner.learn(experience.state, experience.reward)
            except Exception:
                logger.exception("Learner failed online update for experience=%s", experience.experience_id)

        trigger = False
        samples_for_cycle = 0
        with self._lock:
            self._total_samples += 1
            self._samples_since_retrain += 1
            if self._samples_since_retrain >= self.config.retrain_interval_samples:
                trigger = True
                samples_for_cycle = self._samples_since_retrain
                self._samples_since_retrain = 0

        if trigger:
            return self._run_retrain_cycle(samples_for_cycle=samples_for_cycle)
        return None

    def _run_retrain_cycle(self, samples_for_cycle: int) -> EvolutionCycle:
        with self._cycle_lock:
            cycle = EvolutionCycle(samples_since_last_retrain=int(samples_for_cycle))

            if self._learner is not None and self._replay.size() > 0 and hasattr(self._learner, "learn"):
                experiences, _, indices = self._replay.sample(self.config.replay_batch_size)
                td_errors: List[float] = []
                for experience in experiences:
                    try:
                        loss = float(self._learner.learn(experience.state, experience.reward))
                    except Exception:
                        logger.exception("Replay training failed for experience=%s", experience.experience_id)
                        loss = float(experience.td_error)
                    td_errors.append(abs(loss))
                if td_errors and indices:
                    self._replay.update_priorities(indices, td_errors)
                cycle.retrain_triggered = bool(experiences)

            if self._learner is not None and hasattr(self._learner, "get_metrics"):
                try:
                    metrics = self._learner.get_metrics()
                except Exception:
                    logger.exception("Learner metrics retrieval failed")
                    metrics = {}
                cycle.metrics = {
                    key: float(value)
                    for key, value in metrics.items()
                    if isinstance(value, (int, float))
                }
                version = self._versioner.stage(
                    metrics=cycle.metrics,
                    notes=f"Auto-retrain at sample {self._total_samples}",
                )
                if self.config.auto_promote:
                    result = self._versioner.promote(version.version_id)
                    cycle.model_promoted = bool(result.get("promoted", False))
                    cycle.regression_detected = bool(result.get("regression_detected", False))
                    if cycle.regression_detected:
                        logger.warning("Regression detected; triggering rollback")
                        self._versioner.rollback()
                        cycle.model_promoted = False

            with self._lock:
                self._cycles.append(cycle)
                if len(self._cycles) > 1000:
                    self._cycles = self._cycles[-1000:]
                cycle_count = len(self._cycles)

            if cycle_count % self.config.checkpoint_every_cycles == 0:
                try:
                    self.save_checkpoint()
                except Exception:
                    logger.exception("Failed to save evolution checkpoint")
            return cycle

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            active = self._versioner.get_active()
            return {
                "total_samples": self._total_samples,
                "replay_buffer_size": self._replay.size(),
                "active_model": active.model_dump() if active else None,
                "total_retrain_cycles": sum(1 for cycle in self._cycles if cycle.retrain_triggered),
                "total_promotions": sum(1 for cycle in self._cycles if cycle.model_promoted),
                "total_regressions": sum(1 for cycle in self._cycles if cycle.regression_detected),
            }

    def save_checkpoint(self, path: Optional[str] = None) -> str:
        checkpoint_root = Path(path) if path else Path(self.config.checkpoint_dir)
        if checkpoint_root.suffix:
            checkpoint_file = checkpoint_root
            checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            checkpoint_root.mkdir(parents=True, exist_ok=True)
            checkpoint_file = checkpoint_root / f"evolution-{len(self._cycles):06d}.json"
        tmp_file = checkpoint_file.with_suffix(checkpoint_file.suffix + ".tmp")

        learner_checkpoint_path: Optional[str] = None
        if self._learner is not None and hasattr(self._learner, "save_checkpoint"):
            learner_checkpoint_path = str(checkpoint_file.with_name(f"{checkpoint_file.stem}.learner.json"))
            self._learner.save_checkpoint(learner_checkpoint_path)

        with self._lock:
            payload = {
                "config": self.config.model_dump(),
                "total_samples": self._total_samples,
                "samples_since_retrain": self._samples_since_retrain,
                "cycles": [cycle.model_dump() for cycle in self._cycles],
                "replay_state": self._replay.export_state(),
                "versioner_state": self._versioner.export_state(),
                "learner_checkpoint_path": learner_checkpoint_path,
            }
        with tmp_file.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        tmp_file.replace(checkpoint_file)
        return str(checkpoint_file)

    def load_checkpoint(self, path: str) -> None:
        checkpoint_file = Path(path)
        if not checkpoint_file.exists():
            raise FileNotFoundError(f"Evolution checkpoint not found: {checkpoint_file}")
        with checkpoint_file.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        self.config = EvolutionConfig.model_validate(payload.get("config", {}))
        self._replay.load_state(payload.get("replay_state", {}))
        self._versioner.load_state(payload.get("versioner_state", {}))
        with self._lock:
            self._total_samples = int(payload.get("total_samples", 0))
            self._samples_since_retrain = int(payload.get("samples_since_retrain", 0))
            self._cycles = [EvolutionCycle.model_validate(item) for item in payload.get("cycles", [])]

        learner_checkpoint_path = payload.get("learner_checkpoint_path")
        if (
            self._learner is not None
            and isinstance(learner_checkpoint_path, str)
            and learner_checkpoint_path
            and hasattr(self._learner, "load_checkpoint")
            and Path(learner_checkpoint_path).exists()
        ):
            self._learner.load_checkpoint(learner_checkpoint_path)

    def resume_latest(self) -> Optional[str]:
        checkpoint_dir = Path(self.config.checkpoint_dir)
        if checkpoint_dir.suffix:
            if checkpoint_dir.exists():
                self.load_checkpoint(str(checkpoint_dir))
                return str(checkpoint_dir)
            return None
        if not checkpoint_dir.exists():
            return None
        candidates = sorted(checkpoint_dir.glob("evolution-*.json"))
        if not candidates:
            return None
        latest = candidates[-1]
        self.load_checkpoint(str(latest))
        return str(latest)

