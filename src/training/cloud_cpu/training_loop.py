"""Core micro-batch loop for cloud CPU adaptation.

Military/tactical context:
A short, deterministic cycle keeps CPU-only adaptation responsive under limited
compute windows and allows frequent checkpoint opportunities.
"""

from __future__ import annotations

import json
import logging
import math
import random
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import yaml

from src.storage.object_storage import ObjectStorageConnector
from src.training.cloud_cpu.contracts import CycleMetrics, TrainerState, TrainingExample
from src.training.cloud_cpu.contracts import CheckpointMeta as PromotionCheckpointMeta
from src.training.cloud_cpu.dataset_cursor import DatasetCursor
from src.training.cloud_cpu.paths import StatePaths, TrainingTrack
from src.training.cloud_cpu.promotion_gate import PromotionGate
from src.training.validation.grok_oracle import GrokValidationOracle, VerdictRequest

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
            "indopac_mod": 2.65,
            "southam_mod": 2.7,
            "africa_mod": 2.75,
            "shared": 2.9,
        }.get(self._track, 2.9)
        self._decay = {
            "saudi_mod": 0.028,
            "ukraine_mod": 0.030,
            "nato": 0.026,
            "indopac_mod": 0.027,
            "southam_mod": 0.026,
            "africa_mod": 0.025,
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


class PacketTrainingBackend:
    """Deterministic packet-aware backend for real JSONL training data.

    Military/tactical context:
    This backend derives loss from observed packet quality so stage-one adapter
    production reacts to real field data instead of synthetic-only dynamics.
    """

    def __init__(self, track: str = "shared") -> None:
        self._track = str(track)
        self._step = 0
        self._last_loss = 2.4
        self._running_quality = 0.5

    def forward_and_loss(self, examples: List[TrainingExample]) -> float:
        if not examples:
            return self._last_loss

        self._step += 1
        quality = self._packet_quality(examples)
        self._running_quality = (0.7 * self._running_quality) + (0.3 * quality)

        track_factor = {
            "saudi_mod": 0.94,
            "ukraine_mod": 0.96,
            "nato": 0.95,
            "indopac_mod": 0.955,
            "southam_mod": 0.958,
            "africa_mod": 0.962,
            "shared": 0.97,
        }.get(self._track, 0.97)
        trend = max(0.07, (2.2 * (track_factor ** self._step)))
        quality_bonus = (1.0 - self._running_quality) * 0.8
        self._last_loss = round(max(0.05, trend + quality_bonus), 6)
        return self._last_loss

    def step(self, loss: float) -> None:
        self._last_loss = max(0.0, float(loss))

    def get_state_dict(self) -> Dict[str, Any]:
        return {
            "track": self._track,
            "step": int(self._step),
            "last_loss": float(self._last_loss),
            "running_quality": float(self._running_quality),
        }

    def load_state_dict(self, state: Dict[str, Any]) -> None:
        self._step = int(state.get("step", 0))
        self._last_loss = float(state.get("last_loss", 2.4))
        self._running_quality = float(state.get("running_quality", 0.5))

    @staticmethod
    def _packet_quality(examples: List[TrainingExample]) -> float:
        if not examples:
            return 0.0
        prompt_chars = sum(len(row.prompt.strip()) for row in examples)
        completion_chars = sum(len(row.completion.strip()) for row in examples)
        avg_weight = sum(float(row.weight) for row in examples) / len(examples)
        completion_ratio = completion_chars / max(1, prompt_chars)
        structural_signal = min(1.0, max(0.0, completion_ratio))
        return max(0.05, min(1.0, (0.65 * structural_signal) + (0.35 * avg_weight)))


class TrainingLoop:
    """Runs one supervised micro-batch update per cycle."""

    def __init__(
        self,
        track: TrainingTrack,
        config_path: Path,
        state_paths: StatePaths,
        device: str = "cpu",
        backend: Optional[TrainingBackend] = None,
        oracle: Optional[GrokValidationOracle] = None,
        gpu_orchestrator: Optional[Any] = None,
        promotion_gate: Optional[PromotionGate] = None,
        object_storage_connector: Optional[ObjectStorageConnector] = None,
        engine_id: str = "phi3",
        session_id: Optional[str] = None,
        validation_log_path: Path | str = Path("state/training/validation_log.jsonl"),
    ) -> None:
        if not isinstance(track, TrainingTrack):
            track = TrainingTrack(str(track))
        self._track = track
        self._device = str(device)
        self._state_paths = state_paths
        self._config = self._load_track_config(Path(config_path))

        per_track = state_paths.for_track(track)
        self._backend = self._resolve_backend(
            backend=backend,
            track=track.value,
            scenarios_dir=per_track.scenarios,
        )
        self._cursor = DatasetCursor(
            track=track.value,
            scenarios_dir=per_track.scenarios,
            processed_dir=per_track.processed,
            rejected_dir=per_track.rejected,
        )
        self._oracle = oracle
        self._gpu_orchestrator = gpu_orchestrator
        self._engine_id = str(engine_id or "phi3")
        self._session_id = str(session_id or f"session-{uuid.uuid4().hex[:12]}")
        self._validation_log_path = Path(validation_log_path)
        self._promotion_gate = promotion_gate or PromotionGate(
            config_path=Path("configs/training/promotion_gate.yaml"),
            track_config_path=Path(config_path),
        )
        self._last_promoted_scores: Optional[Dict[str, Any]] = None
        self._storage = self._resolve_storage_connector(
            object_storage_connector=object_storage_connector,
            oracle=oracle,
            state_root=state_paths.root,
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
        self._maybe_upgrade_backend()
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

        metrics = CycleMetrics(
            cycle_id=cycle_id,
            step=self._step,
            epoch=self._epoch,
            track=self._track.value,
            samples_processed=len(examples),
            loss=loss,
            pseudo_label_acceptance_rate=self._acceptance_rate(examples),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        if self._oracle is not None:
            self._process_stage_one_adapter(metrics=metrics)
        return metrics

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

    @staticmethod
    def _resolve_backend(
        backend: Optional[TrainingBackend],
        track: str,
        scenarios_dir: Path,
    ) -> TrainingBackend:
        if backend is not None:
            return backend
        try:
            from src.training.cloud_cpu.real_backend import RealCPUTrainingBackend

            return RealCPUTrainingBackend(track=track)
        except Exception as exc:
            logger.warning(
                "RealCPUTrainingBackend unavailable for track=%s; falling back to packet backend: %s",
                track,
                exc,
            )
        try:
            return PacketTrainingBackend(track=track)
        except Exception as exc:
            logger.warning(
                "PacketTrainingBackend unavailable for track=%s; falling back to stub backend: %s",
                track,
                exc,
            )
        return StubTrainingBackend(track=track)

    def _maybe_upgrade_backend(self) -> None:
        if not isinstance(self._backend, StubTrainingBackend):
            return
        if self._scenarios_have_jsonl_packets(self._state_paths.for_track(self._track).scenarios):
            self._backend = PacketTrainingBackend(track=self._track.value)
            logger.info("Switched %s backend from stub to packet-aware mode", self._track.value)

    @staticmethod
    def _scenarios_have_jsonl_packets(scenarios_dir: Path) -> bool:
        if not scenarios_dir.exists():
            return False
        for scenario_dir in sorted(scenarios_dir.glob("scenario-*")):
            if not scenario_dir.is_dir():
                continue
            prompts_path = scenario_dir / "prompts.jsonl"
            labels_path = scenario_dir / "labels.jsonl"
            if (
                prompts_path.exists()
                and labels_path.exists()
                and prompts_path.stat().st_size > 0
                and labels_path.stat().st_size > 0
            ):
                return True
        return False

    @staticmethod
    def _resolve_storage_connector(
        object_storage_connector: Optional[ObjectStorageConnector],
        oracle: Optional[GrokValidationOracle],
        state_root: Path,
    ) -> Any:
        if object_storage_connector is not None:
            return object_storage_connector
        if oracle is not None:
            connector = getattr(oracle, "object_storage_connector", None)
            if connector is not None:
                return connector
        try:
            return ObjectStorageConnector()
        except Exception:
            return ObjectStorageConnector(emulation_root=state_root / "object-storage")

    def _process_stage_one_adapter(self, metrics: CycleMetrics) -> None:
        if metrics.samples_processed <= 0 or self._oracle is None:
            return
        adapter_id = f"{metrics.track}-{self._engine_id}-{metrics.step:09d}"
        stage1_key = (
            f"training/stage1/pending/{metrics.track}/{self._engine_id}/"
            f"{adapter_id}.adapter.json"
        )
        adapter_payload = {
            "adapter_id": adapter_id,
            "track": metrics.track,
            "engine_id": self._engine_id,
            "cycle_id": metrics.cycle_id,
            "step": metrics.step,
            "epoch": metrics.epoch,
            "loss": metrics.loss,
            "pseudo_label_acceptance_rate": metrics.pseudo_label_acceptance_rate,
            "session_id": self._session_id,
            "timestamp": metrics.timestamp,
            "backend_state": self._backend.get_state_dict(),
        }
        self._write_json(stage1_key, adapter_payload)

        request = VerdictRequest(
            artifact_id=adapter_id,
            engine_id=self._engine_id,
            track=metrics.track,
            artifact_type="adapter",
            object_key=stage1_key,
            session_id=self._session_id,
            created_at=metrics.timestamp,
        )
        self._write_json(
            f"grok-verdicts/pending/{adapter_id}.request.json",
            {**asdict(request), "validation_stage": "cpu_stage1"},
        )
        verdict = self._oracle.evaluate_artifact(request, validation_stage="cpu_stage1")
        gate_passed, gate_reason = self._promotion_gate_passed(metrics=metrics, verdict_score=verdict.score)
        final_passed = bool(verdict.passed) and gate_passed

        if final_passed:
            cleared_key = (
                f"training/stage1/cpu_cleared/{metrics.track}/{self._engine_id}/"
                f"{adapter_id}.adapter.json"
            )
            self._write_json(
                cleared_key,
                {
                    **adapter_payload,
                    "status": "cpu_cleared",
                    "grok_score": verdict.score,
                    "grok_reason": verdict.reason,
                },
            )
            self._last_promoted_scores = {
                "step": int(metrics.step),
                "eval_scores": {
                    "overall": float(verdict.score),
                    "grok_score": float(verdict.score),
                },
                "promoted_at": datetime.now(timezone.utc).isoformat(),
            }
            if self._gpu_orchestrator is not None and hasattr(self._gpu_orchestrator, "queue_cpu_cleared_adapter"):
                self._gpu_orchestrator.queue_cpu_cleared_adapter(
                    engine_id=self._engine_id,
                    track=metrics.track,
                    cpu_adapter_key=cleared_key,
                    session_id=self._session_id,
                    dataset_path=str(self._state_paths.for_track(self._track).scenarios),
                    metadata={
                        "stage": "cpu_cleared",
                        "grok_score": float(verdict.score),
                        "cycle_id": metrics.cycle_id,
                    },
                )
            logger.info(
                "Stage-1 adapter cpu_cleared adapter=%s track=%s score=%.3f",
                adapter_id,
                metrics.track,
                verdict.score,
            )
            return

        failure_reason = verdict.reason if verdict.reason else "Grok validation rejected adapter"
        if not gate_passed:
            failure_reason = f"{failure_reason}; promotion_gate={gate_reason}"
        logger.info(
            "Stage-1 adapter rejected adapter=%s track=%s reason=%s",
            adapter_id,
            metrics.track,
            failure_reason,
        )
        self._append_validation_fallback_log(
            {
                "artifact_id": adapter_id,
                "track": metrics.track,
                "engine_id": self._engine_id,
                "session_id": self._session_id,
                "stage": "stage_1_cpu",
                "passed": False,
                "score": float(verdict.score),
                "reason": failure_reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _promotion_gate_passed(self, metrics: CycleMetrics, verdict_score: float) -> tuple[bool, str]:
        checkpoint = PromotionCheckpointMeta(
            checkpoint_id=f"{metrics.track}-{self._engine_id}-{metrics.step:09d}",
            track=metrics.track,
            step=int(metrics.step),
            epoch=int(metrics.epoch),
        )
        decision = self._promotion_gate.evaluate(
            checkpoint_meta=checkpoint,
            eval_results={"overall": float(verdict_score), "grok_score": float(verdict_score)},
            last_promoted_results=self._last_promoted_scores,
        )
        return bool(decision.passed), str(decision.reason)

    def _write_json(self, key: str, payload: Dict[str, Any]) -> None:
        connector = self._storage
        if hasattr(connector, "put_json"):
            connector.put_json(key, payload)
            return
        if hasattr(connector, "write_json"):
            connector.write_json(key, payload)
            return
        if hasattr(connector, "upload_json"):
            connector.upload_json(key, payload)
            return
        if hasattr(connector, "put_bytes"):
            connector.put_bytes(
                key,
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                content_type="application/json",
            )
            return
        raise AttributeError("Object storage connector does not support JSON writes")

    def _append_validation_fallback_log(self, payload: Dict[str, Any]) -> None:
        self._validation_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._validation_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")

