"""Core micro-batch loop for cloud CPU adaptation.

Military/tactical context:
A short, deterministic cycle keeps CPU-only adaptation responsive under limited
compute windows and allows frequent checkpoint opportunities.
"""

from __future__ import annotations

import logging
import math
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import yaml

from src.training.cloud_cpu.contracts import CycleMetrics, TrainerState, TrainingExample
from src.training.cloud_cpu.dataset_cursor import DatasetCursor
from src.training.cloud_cpu.paths import StatePaths, TrainingTrack

logger = logging.getLogger("s3m.training.cloud_cpu.training_loop")


@runtime_checkable
class TrainingBackend(Protocol):
    """Abstraction for model/update implementations."""

    def forward_and_loss(self, examples: List[TrainingExample]) -> float: ...

    def step(self, loss: float) -> None: ...

    def get_state_dict(self) -> Dict[str, Any]: ...

    def load_state_dict(self, state: Dict[str, Any]) -> None: ...


class StubTrainingBackend:
    """Synthetic backend that mimics improving loss over time."""

    def __init__(self, track: str = "shared") -> None:
        self._track = str(track)
        self._step = 0
        self._last_loss = 3.0
        self._rng = random.Random(f"s3m-stub-{self._track}")
        self._track_baseline = {
            "saudi_mod": 2.8,
            "ukraine_mod": 2.6,
            "nato": 2.7,
            "shared": 2.9,
        }.get(self._track, 2.9)
        self._decay = {
            "saudi_mod": 0.028,
            "ukraine_mod": 0.030,
            "nato": 0.026,
            "shared": 0.022,
        }.get(self._track, 0.022)

    def forward_and_loss(self, examples: List[TrainingExample]) -> float:
        if not examples:
            return self._last_loss
        self._step += 1

        avg_prompt_chars = sum(len(example.prompt) for example in examples) / max(1, len(examples))
        complexity_penalty = min(0.35, avg_prompt_chars / 4_000.0)

        # Tactical realism: contested datasets often show slight oscillation.
        oscillation = 0.04 * math.sin(self._step / 11.0)
        noise = self._rng.uniform(-0.015, 0.015)
        trend = self._track_baseline * math.exp(-self._decay * self._step)
        self._last_loss = max(0.08, trend + complexity_penalty + oscillation + noise)
        return float(self._last_loss)

    def step(self, loss: float) -> None:
        # The stub records loss for checkpoint continuity.
        self._last_loss = max(0.0, float(loss))

    def get_state_dict(self) -> Dict[str, Any]:
        return {
            "track": self._track,
            "step": int(self._step),
            "last_loss": float(self._last_loss),
            "rng_state": self._rng.getstate(),
        }

    def load_state_dict(self, state: Dict[str, Any]) -> None:
        self._step = int(state.get("step", 0))
        self._last_loss = float(state.get("last_loss", self._track_baseline))
        rng_state = state.get("rng_state")
        if rng_state is not None:
            self._rng.setstate(rng_state)


class TrainingLoop:
    """Runs one supervised micro-batch update per cycle."""

    def __init__(
        self,
        track: TrainingTrack,
        config_path: Path,
        state_paths: StatePaths,
        device: str = "cpu",
        backend: Optional[TrainingBackend] = None,
    ) -> None:
        if not isinstance(track, TrainingTrack):
            track = TrainingTrack(str(track))
        self._track = track
        self._device = str(device)
        self._state_paths = state_paths
        self._config = self._load_track_config(Path(config_path))
        self._backend = backend or StubTrainingBackend(track=track.value)

        per_track = state_paths.for_track(track)
        self._cursor = DatasetCursor(
            track=track.value,
            scenarios_dir=per_track.scenarios,
            processed_dir=per_track.processed,
            rejected_dir=per_track.rejected,
        )

        self._step = 0
        self._epoch = 0
        self._last_loss = 0.0
        self._total_samples = 0

    @property
    def cursor(self) -> DatasetCursor:
        return self._cursor

    @property
    def backend(self) -> TrainingBackend:
        return self._backend

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    def run_cycle(self) -> CycleMetrics:
        """Execute one training cycle and return metrics."""
        batch_size = int(self._training_cfg("micro_batch_size", 4))
        cycle_id = f"cycle-{uuid.uuid4().hex[:10]}"
        cycle_started = time.monotonic()
        examples = self._cursor.next_batch(batch_size=batch_size)
        if not examples:
            idle_sleep_ms = int(self._training_cfg("idle_sleep_ms", 0))
            if idle_sleep_ms > 0:
                time.sleep(idle_sleep_ms / 1000.0)
            return CycleMetrics(
                cycle_id=cycle_id,
                step=self._step,
                epoch=self._epoch,
                track=self._track.value,
                samples_processed=0,
                loss=0.0,
                pseudo_label_acceptance_rate=0.0,
            )

        # Lightweight supervised update delegated to configured backend.
        loss = float(self._backend.forward_and_loss(examples))
        self._backend.step(loss)

        self._step += 1
        self._last_loss = loss
        self._total_samples += len(examples)

        steps_per_epoch = max(1, int(self._training_cfg("steps_per_epoch", 100)))
        self._epoch = self._step // steps_per_epoch
        elapsed = time.monotonic() - cycle_started
        logger.debug(
            "Cycle %s completed track=%s step=%s samples=%s loss=%.4f elapsed=%.3fs",
            cycle_id,
            self._track.value,
            self._step,
            len(examples),
            loss,
            elapsed,
        )

        return CycleMetrics(
            cycle_id=cycle_id,
            step=self._step,
            epoch=self._epoch,
            track=self._track.value,
            samples_processed=len(examples),
            loss=loss,
            pseudo_label_acceptance_rate=self._acceptance_rate(examples),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def export_state(self) -> TrainerState:
        state = TrainerState(
            step=self._step,
            epoch=self._epoch,
            last_loss=self._last_loss,
            total_samples=self._total_samples,
            backend_state=self._backend.get_state_dict(),
            metadata={"track": self._track.value, "device": self._device},
        )
        self._cursor.save_to_state(state)
        return state

    def restore_state(self, state: TrainerState) -> None:
        self._step = int(state.step)
        self._epoch = int(state.epoch)
        self._last_loss = float(state.last_loss)
        self._total_samples = int(state.total_samples)
        self._cursor.restore_cursor(state.dataset_cursor)
        self._backend.load_state_dict(state.backend_state)

    def _training_cfg(self, key: str, default: Any) -> Any:
        training_cfg = self._config.get("training", {})
        if not isinstance(training_cfg, dict):
            return default
        return training_cfg.get(key, default)

    @staticmethod
    def _acceptance_rate(examples: List[TrainingExample]) -> float:
        if not examples:
            return 0.0
        accepted = sum(1 for row in examples if float(row.weight) >= 0.5)
        return accepted / len(examples)

    @staticmethod
    def _load_track_config(config_path: Path) -> Dict[str, Any]:
        if not config_path.exists():
            logger.warning("Missing cloud CPU track config at %s; using defaults", config_path)
            return {}
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ValueError("track config must be a dictionary")
        return data

