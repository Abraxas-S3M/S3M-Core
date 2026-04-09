"""RunPod GPU session lifecycle manager for S3M QLoRA operations.

Military/tactical context:
This module coordinates short, high-intensity training sorties on leased GPUs,
then immediately exfiltrates adapter intelligence artifacts back to sovereign
storage so progress is preserved between disconnected deployment windows.
"""

from __future__ import annotations

import importlib
import json
import logging
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from src.training.gpu.config import GPUTrainingConfig
from src.training.gpu.eval_harness import EvalResult, S3MEvalHarness
from src.training.gpu.lora_trainer import S3MLoRATrainer

logger = logging.getLogger("s3m.training.gpu.session_manager")

GROK_BLOCK_MESSAGE = (
    "Grok-300B is too large for GPU training. "
    "It remains in BackBlaze as a validation oracle only."
)
SUPPORTED_TRACKS = {"saudi_mod", "ukraine_mod", "nato"}
ENGINE_ALIASES = {
    "phi3-medium": "phi3",
    "phi3": "phi3",
    "mistral-7b": "mistral",
    "mistral": "mistral",
}


@dataclass
class SessionResult:
    engine_id: str
    track: str
    adapter_path: str
    final_loss: float
    eval_scores: Dict[str, float]
    training_duration_seconds: float
    examples_processed: int
    uploaded_to_b2: bool


class GrokTrainingBlockedError(ValueError):
    """Raised when a Grok-family engine is routed to GPU fine-tuning."""


class _LocalB2MirrorConnector:
    """Offline fallback connector mirroring B2 keys onto local filesystem."""

    def __init__(self, mirror_root: str = "/workspace/backblaze") -> None:
        self.root = Path(mirror_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def sync_prefix_to_local(self, prefix: str, local_dir: str) -> bool:
        src = self.root / prefix.strip("/")
        dest = Path(local_dir)
        dest.mkdir(parents=True, exist_ok=True)
        if not src.exists():
            return False
        self._copy_tree(src, dest)
        return True

    def sync_local_to_prefix(self, local_dir: str, prefix: str) -> bool:
        src = Path(local_dir)
        if not src.exists():
            return False
        dest = self.root / prefix.strip("/")
        dest.mkdir(parents=True, exist_ok=True)
        self._copy_tree(src, dest)
        return True

    def list_prefix(self, prefix: str) -> list[str]:
        base = self.root / prefix.strip("/")
        if not base.exists():
            return []
        if base.is_file():
            return [prefix.strip("/")]
        out: list[str] = []
        for path in base.rglob("*"):
            if path.is_file():
                out.append(str(path.relative_to(self.root)))
        return out

    def write_json(self, key: str, payload: Dict[str, Any]) -> bool:
        target = self.root / key.strip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return True

    @staticmethod
    def _copy_tree(src: Path, dest: Path) -> None:
        for path in src.rglob("*"):
            rel = path.relative_to(src)
            target = dest / rel
            if path.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


@dataclass(frozen=True)
class _ResolvedEngine:
    requested_id: str
    trainer_engine_id: str
    eval_engine_id: str
    storage_engine_id: str


class GPUSessionManager:
    """Manages RunPod GPU training sessions for S3M engines."""

    def __init__(self, config_path: str = "configs/gpu_training.yaml"):
        self.config_path = config_path
        self.config = GPUTrainingConfig.from_yaml(config_path)
        self.workspace_root = Path("/workspace")
        self.base_weights_root = self.workspace_root / "base_weights"
        self.dataset_root = self.workspace_root / "datasets"
        self.checkpoint_root = self.workspace_root / "checkpoints" / "runpod"
        self.eval_root = self.workspace_root / "eval-results"
        self.eval_harness = S3MEvalHarness(eval_data_dir=str(self.eval_root))
        self.b2_connector = self._load_b2_connector()
        self._last_session_metadata_path: Optional[Path] = None
        self._last_checkpoint_for_resume: Optional[str] = None
        self._last_eval_scores: Dict[str, float] = {}
        self._validate_engine_targets()

    def launch_session(
        self,
        engine_id: str,
        track: str,
        max_runtime_hours: float = 4.0,
        dataset_override: Optional[str] = None,
    ) -> SessionResult:
        """Full training session lifecycle:
        1. Validate engine_id is NOT grok (hard block)
        2. Sync weights + datasets from BackBlaze
        3. Run QLoRA fine-tuning
        4. Run eval harness
        5. Push adapter + metrics to BackBlaze
        6. Push to grok-verdicts/pending/ for Grok validation
        7. Return session results
        """

        self._assert_non_grok(engine_id)
        self._validate_track(track)
        if max_runtime_hours <= 0:
            raise ValueError("max_runtime_hours must be greater than 0.")

        resolved = self._resolve_engine(engine_id)
        self.sync_from_b2(resolved.storage_engine_id, track)
        resumed_from = self._detect_and_offer_resume_checkpoint(resolved.storage_engine_id)
        dataset_path = self._resolve_dataset_path(track=track, dataset_override=dataset_override)

        run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_name = f"s3m-{resolved.trainer_engine_id}-{track}-{run_stamp}"
        trainer = S3MLoRATrainer(
            engine_id=resolved.trainer_engine_id,
            config=self.config,
            output_dir=str(self.checkpoint_root / resolved.storage_engine_id),
            run_name=run_name,
        )

        metrics = trainer.train(
            dataset_path=dataset_path,
            resume_from=resumed_from,
            max_runtime_seconds=max_runtime_hours * 3600.0,
        )
        if metrics.get("time_limit_reached"):
            logger.warning("Session time limit reached. Checkpoint saved for resume.")

        adapter_path = str(metrics.get("adapter_path", ""))
        if not adapter_path:
            raise RuntimeError("Training completed without producing an adapter path.")

        eval_result = self._run_eval(
            eval_engine_id=resolved.eval_engine_id,
            adapter_path=adapter_path,
        )
        self._last_eval_scores = dict(eval_result.scores)

        metadata_path = self._write_session_metadata(
            engine_id=resolved.storage_engine_id,
            track=track,
            duration=float(metrics.get("elapsed_seconds", 0.0)),
            final_loss=metrics.get("final_loss"),
            eval_scores=eval_result.scores,
            adapter_path=adapter_path,
            resumed_from=resumed_from,
        )
        self._last_session_metadata_path = metadata_path
        self._last_checkpoint_for_resume = metrics.get("checkpoint_path")

        uploaded_to_b2 = self.sync_to_b2(
            engine_id=resolved.storage_engine_id,
            track=track,
            adapter_dir=Path(adapter_path),
        )
        return SessionResult(
            engine_id=resolved.storage_engine_id,
            track=track,
            adapter_path=adapter_path,
            final_loss=float(metrics.get("final_loss") or 0.0),
            eval_scores=dict(eval_result.scores),
            training_duration_seconds=float(metrics.get("elapsed_seconds", 0.0)),
            examples_processed=int(metrics.get("examples_processed", 0)),
            uploaded_to_b2=uploaded_to_b2,
        )

    def sync_from_b2(self, engine_id: str, track: str):
        """Pull base weights and training data from BackBlaze."""
        self._assert_non_grok(engine_id)
        self._validate_track(track)
        weights_prefix = f"base-weights/{engine_id}/"
        dataset_prefix = f"datasets/{track}/scenarios/"
        weights_dest = self.base_weights_root / engine_id
        dataset_dest = self.dataset_root / track
        self._pull_prefix(weights_prefix, weights_dest)
        self._pull_prefix(dataset_prefix, dataset_dest)
        logger.info("B2 sync complete: engine=%s track=%s", engine_id, track)

    def sync_to_b2(self, engine_id: str, track: str, adapter_dir: Path):
        """Push training artifacts back to BackBlaze."""
        self._assert_non_grok(engine_id)
        self._validate_track(track)

        upload_results = []
        upload_results.append(self._push_prefix(adapter_dir, f"adapters/{engine_id}/{track}/"))

        checkpoint_source = self._resolve_checkpoint_upload_path(engine_id=engine_id, adapter_dir=adapter_dir)
        if checkpoint_source is not None:
            upload_results.append(self._push_prefix(checkpoint_source, f"checkpoints/runpod/{engine_id}/"))

        eval_dir = self.eval_root / engine_id / track
        if eval_dir.exists():
            upload_results.append(self._push_prefix(eval_dir, f"eval-results/{engine_id}/{track}/"))

        verdict_timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        verdict_key = f"grok-verdicts/pending/session-{verdict_timestamp}.json"
        verdict_payload = {
            "engine_id": engine_id,
            "track": track,
            "adapter_path": str(adapter_dir),
            "eval_scores": self._last_eval_scores,
            "metadata_path": str(self._last_session_metadata_path) if self._last_session_metadata_path else None,
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }
        upload_results.append(self._write_json(verdict_key, verdict_payload))
        return all(upload_results) if upload_results else False

    def _validate_engine_targets(self) -> None:
        if not self.config.engines:
            raise ValueError("No engine definitions found in GPU training config.")
        canonical = {ENGINE_ALIASES.get(name.lower(), name.lower()) for name in self.config.engines}
        required = {"phi3", "mistral"}
        missing = sorted(required - canonical)
        if missing:
            raise ValueError(
                f"Config missing required engine targets: {missing}. "
                f"Available: {sorted(self.config.engines.keys())}"
            )

    def _validate_track(self, track: str) -> None:
        if track not in SUPPORTED_TRACKS:
            raise ValueError(f"Unsupported track '{track}'. Allowed: {sorted(SUPPORTED_TRACKS)}")

    @staticmethod
    def _assert_non_grok(engine_id: str) -> None:
        if "grok" in engine_id.strip().lower():
            raise GrokTrainingBlockedError(GROK_BLOCK_MESSAGE)

    def _resolve_engine(self, engine_id: str) -> _ResolvedEngine:
        self._assert_non_grok(engine_id)
        requested = engine_id.strip().lower()
        canonical = ENGINE_ALIASES.get(requested, requested)

        candidates = [
            requested,
            canonical,
            requested.replace("_", "-"),
            requested.replace("-", "_"),
            canonical.replace("_", "-"),
            canonical.replace("-", "_"),
        ]
        trainer_engine = next((candidate for candidate in candidates if candidate in self.config.engines), None)
        if trainer_engine is None:
            raise ValueError(
                f"Engine '{engine_id}' is not configured. "
                f"Available targets: {sorted(self.config.engines.keys())}"
            )
        return _ResolvedEngine(
            requested_id=requested,
            trainer_engine_id=trainer_engine,
            eval_engine_id=canonical,
            storage_engine_id=requested,
        )

    def _resolve_dataset_path(self, track: str, dataset_override: Optional[str]) -> str:
        if dataset_override:
            override = Path(dataset_override)
            if not override.exists():
                raise FileNotFoundError(f"Dataset override path not found: {dataset_override}")
            return str(override)

        dataset_dir = self.dataset_root / track
        preferred = [
            dataset_dir / "train.jsonl",
            dataset_dir / "train.json",
            dataset_dir / "scenarios.jsonl",
            dataset_dir / "scenarios.json",
        ]
        for candidate in preferred:
            if candidate.exists():
                return str(candidate)

        json_files = sorted(dataset_dir.glob("*.jsonl")) + sorted(dataset_dir.glob("*.json"))
        if json_files:
            return str(json_files[0])
        if dataset_dir.exists():
            return str(dataset_dir)
        raise FileNotFoundError(
            f"No dataset found for track '{track}'. Expected files under: {dataset_dir}"
        )

    def _run_eval(self, eval_engine_id: str, adapter_path: str) -> EvalResult:
        return self.eval_harness.evaluate(
            engine_id=eval_engine_id,
            model_path=adapter_path,
        )

    def _write_session_metadata(
        self,
        engine_id: str,
        track: str,
        duration: float,
        final_loss: Optional[float],
        eval_scores: Dict[str, float],
        adapter_path: str,
        resumed_from: Optional[str],
    ) -> Path:
        target_dir = self.eval_root / engine_id / track
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        metadata_path = target_dir / f"session-{stamp}.json"
        payload = {
            "engine_id": engine_id,
            "track": track,
            "duration": round(duration, 3),
            "final_loss": float(final_loss) if final_loss is not None else None,
            "eval_scores": eval_scores,
            "adapter_path": adapter_path,
            "resumed_from": resumed_from,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        metadata_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return metadata_path

    def _detect_and_offer_resume_checkpoint(self, engine_id: str) -> Optional[str]:
        self._assert_non_grok(engine_id)
        local_checkpoint_root = self.checkpoint_root / engine_id
        local_checkpoint_root.mkdir(parents=True, exist_ok=True)
        self._pull_prefix(f"checkpoints/runpod/{engine_id}/", local_checkpoint_root)

        checkpoint_dirs = self._collect_checkpoint_dirs(local_checkpoint_root)
        if not checkpoint_dirs:
            return None

        latest = checkpoint_dirs[0]
        if sys.stdin.isatty():
            decision = input(f"Resume from checkpoint '{latest}'? [Y/n]: ").strip().lower()
            if decision not in {"", "y", "yes"}:
                logger.info("Resume checkpoint declined: %s", latest)
                return None
        else:
            logger.info("Resume checkpoint found and auto-selected: %s", latest)
        return str(latest)

    @staticmethod
    def _collect_checkpoint_dirs(root: Path) -> list[Path]:
        candidates = [
            path
            for path in root.rglob("*")
            if path.is_dir() and (path.name.startswith("checkpoint-") or path.name == "time_limit_checkpoint")
        ]
        return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)

    def _resolve_checkpoint_upload_path(self, engine_id: str, adapter_dir: Path) -> Optional[Path]:
        if self._last_checkpoint_for_resume:
            checkpoint_path = Path(self._last_checkpoint_for_resume)
            if checkpoint_path.exists():
                return checkpoint_path
        run_dir = adapter_dir.parent
        if run_dir.exists():
            return run_dir
        engine_checkpoint_dir = self.checkpoint_root / engine_id
        if engine_checkpoint_dir.exists():
            return engine_checkpoint_dir
        return None

    def _pull_prefix(self, prefix: str, destination: Path) -> bool:
        destination.mkdir(parents=True, exist_ok=True)
        method = self._get_connector_method(
            ["sync_prefix_to_local", "download_prefix", "pull_prefix", "sync_from_b2", "download_folder"]
        )
        if method is None:
            return False
        return self._invoke_method(
            method=method,
            positional=(prefix, str(destination)),
            keyword_options=[
                {"prefix": prefix, "local_dir": str(destination)},
                {"prefix": prefix, "destination": str(destination)},
                {"remote_prefix": prefix, "local_path": str(destination)},
                {"source_prefix": prefix, "dest_dir": str(destination)},
            ],
        )

    def _push_prefix(self, source: Path, prefix: str) -> bool:
        if not source.exists():
            return False
        method = self._get_connector_method(
            ["sync_local_to_prefix", "upload_dir", "push_dir", "sync_to_b2", "upload_folder"]
        )
        if method is None:
            return False
        return self._invoke_method(
            method=method,
            positional=(str(source), prefix),
            keyword_options=[
                {"local_dir": str(source), "prefix": prefix},
                {"source_dir": str(source), "prefix": prefix},
                {"local_path": str(source), "remote_prefix": prefix},
                {"source": str(source), "destination_prefix": prefix},
            ],
        )

    def _write_json(self, key: str, payload: Dict[str, Any]) -> bool:
        method = self._get_connector_method(["write_json", "upload_json", "put_json"])
        if method is None:
            return False
        return self._invoke_method(
            method=method,
            positional=(key, payload),
            keyword_options=[
                {"key": key, "payload": payload},
                {"path": key, "payload": payload},
                {"key": key, "data": payload},
            ],
        )

    def _load_b2_connector(self) -> Any:
        try:
            module = importlib.import_module("src.storage.b2_connector")
            for name in ("B2Connector", "BackBlazeB2Connector", "BackblazeB2Connector"):
                connector_cls = getattr(module, name, None)
                if connector_cls is None:
                    continue
                try:
                    return connector_cls()
                except TypeError:
                    # Keep constructor fallback generic for compatibility with Prompt #1 variants.
                    return connector_cls(config_path=self.config_path)
        except Exception as exc:
            logger.warning("B2 connector unavailable; using local mirror fallback. reason=%s", exc)
        return _LocalB2MirrorConnector()

    def _get_connector_method(self, method_names: Iterable[str]):
        for name in method_names:
            candidate = getattr(self.b2_connector, name, None)
            if callable(candidate):
                return candidate
        logger.warning("No compatible B2 connector method found for names=%s", list(method_names))
        return None

    @staticmethod
    def _invoke_method(
        method: Any,
        positional: tuple[Any, ...],
        keyword_options: list[Dict[str, Any]],
    ) -> bool:
        try:
            result = method(*positional)
            return bool(result) if result is not None else True
        except TypeError:
            pass
        for option in keyword_options:
            try:
                result = method(**option)
                return bool(result) if result is not None else True
            except TypeError:
                continue
        return False

