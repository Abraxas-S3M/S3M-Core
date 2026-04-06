#!/usr/bin/env python3
"""S3M background worker for offline tactical learning operations.

This process handles replay ingestion, self-training, checkpointing, and
evaluation in a long-running loop. It deliberately avoids serving web traffic.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add project root so script works when run directly from /scripts.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_int_env(name: str, default: int) -> int:
    """Read an integer env var with safe fallback."""
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


DEPLOYMENT_MODE = os.environ.get("DEPLOYMENT_MODE", "jetson_edge")
DEVICE = os.environ.get("S3M_DEVICE", "cpu").strip().lower()
WORKER_INTERVAL = _read_int_env("S3M_WORKER_INTERVAL_SECONDS", 300)
DATA_DIR = Path(os.environ.get("S3M_DATA_DIR", "data"))
CHECKPOINT_DIR = DATA_DIR / "checkpoints"
REPLAY_DIR = DATA_DIR / "replays"
LOG_DIR = DATA_DIR / "logs"

_shutdown_requested = False
logger = logging.getLogger("s3m.worker")


def _configure_logging() -> None:
    """Configure stdout + file logging for worker telemetry."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)

    level_name = os.environ.get("S3M_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler = logging.FileHandler(LOG_DIR / "worker.log")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logger.setLevel(level)
    logger.propagate = False
    logger.handlers.clear()
    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)


def _handle_signal(signum: int, _frame: Any) -> None:
    """Request clean shutdown on container stop signals."""
    global _shutdown_requested
    logger.info("Received signal %s; beginning graceful shutdown", signum)
    _shutdown_requested = True


def _register_signal_handlers() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def _scan_replay_data() -> list[Path]:
    """Find unprocessed replay files for tactical learning updates."""
    if not REPLAY_DIR.exists():
        return []
    replay_files = sorted(REPLAY_DIR.glob("*.jsonl"))
    return [path for path in replay_files if not path.with_suffix(".processed").exists()]


def _parse_feature_vector(raw_features: Any) -> list[float] | None:
    """Validate feature vectors before using them for model updates."""
    if not isinstance(raw_features, list) or not raw_features:
        return None

    parsed: list[float] = []
    for value in raw_features:
        if isinstance(value, bool):
            return None
        if not isinstance(value, (int, float)):
            return None
        parsed.append(float(value))
    return parsed


def _run_self_training_cycle(replay_files: list[Path]) -> dict[str, Any]:
    """Execute one self-training cycle using replay-derived feature payloads."""
    result: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files_processed": 0,
        "samples_trained": 0,
        "status": "skipped",
    }
    if not replay_files:
        return result

    try:
        import numpy as np
        from src.edge_compute.models import SelfTrainingStrategy
        from src.edge_compute.self_training import NumpyLinearModel, SelfTrainingEngine

        all_features: list[list[float]] = []
        for replay_file in replay_files:
            try:
                with replay_file.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        record = json.loads(line)
                        features = _parse_feature_vector(record.get("features"))
                        if features is not None:
                            all_features.append(features)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Skipping unreadable replay file %s: %s", replay_file, exc)

        if not all_features:
            result["status"] = "no_data"
            logger.info("Replay data present but no valid features were found")
            return result

        # Defensive shape check to keep tactical training batches coherent.
        input_dim = len(all_features[0])
        valid_features = [row for row in all_features if len(row) == input_dim]
        if not valid_features:
            result["status"] = "no_data"
            logger.info("No replay features passed shape validation")
            return result

        unlabeled_x = np.asarray(valid_features, dtype=np.float32)
        seed_count = min(16, unlabeled_x.shape[0])
        labeled_x = unlabeled_x[:seed_count]
        labeled_y = np.zeros((seed_count,), dtype=np.int64)

        model = NumpyLinearModel(
            input_dim=input_dim,
            hidden_dim=max(8, min(64, input_dim * 2)),
            output_dim=3,
        )
        engine = SelfTrainingEngine(strategy=SelfTrainingStrategy.NOISY_STUDENT)
        engine.initialize(model)
        batch = engine.train_cycle(
            labeled_x=labeled_x,
            labeled_y=labeled_y,
            unlabeled_x=unlabeled_x,
            epochs=1,
        )

        result["files_processed"] = len(replay_files)
        result["samples_trained"] = int(unlabeled_x.shape[0])
        result["status"] = "completed"
        result["batch"] = {
            "cycle_id": batch.cycle_id,
            "sample_count": batch.sample_count,
            "avg_confidence": batch.avg_confidence,
            "noise_applied": batch.noise_applied,
        }

        for replay_file in replay_files:
            replay_file.with_suffix(".processed").touch(exist_ok=True)

        logger.info(
            "Self-training cycle complete: files=%d samples=%d",
            result["files_processed"],
            result["samples_trained"],
        )
        return result
    except ImportError as exc:
        result["status"] = "module_unavailable"
        result["error"] = str(exc)
        logger.warning("Self-training dependencies unavailable: %s", exc)
    except Exception as exc:  # pragma: no cover - defensive worker guardrail
        result["status"] = "error"
        result["error"] = str(exc)
        logger.error("Self-training cycle failed: %s", exc, exc_info=True)
    return result


def _save_checkpoint(cycle_result: dict[str, Any]) -> str | None:
    """Persist a checkpoint after successful cycle completion."""
    if cycle_result.get("status") != "completed":
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = CHECKPOINT_DIR / f"checkpoint_{timestamp}.json"
    payload = {
        "timestamp": timestamp,
        "deployment_mode": DEPLOYMENT_MODE,
        "device": DEVICE,
        "training_result": cycle_result,
    }

    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    logger.info("Checkpoint saved: %s", path)
    return str(path)


def _run_evaluation(checkpoint_path: str) -> dict[str, Any]:
    """Run lightweight post-checkpoint evaluation telemetry."""
    result: dict[str, Any] = {
        "checkpoint": checkpoint_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "completed",
        "metrics": {
            "device": DEVICE,
            "checkpoint_size_bytes": os.path.getsize(checkpoint_path),
        },
    }

    try:
        from src.edge_compute.self_training import SelfTrainingEngine

        _ = SelfTrainingEngine
        result["metrics"]["training_module_available"] = True
    except ImportError:
        result["metrics"]["training_module_available"] = False
        result["status"] = "partial"

    # Tactical edge rule: avoid GPU-only probing in explicit CPU mode.
    if DEVICE == "cpu":
        result["metrics"]["gpu_probe_skipped"] = True
    else:
        try:
            import torch

            result["metrics"]["cuda_available"] = bool(torch.cuda.is_available())
        except ImportError:
            result["metrics"]["cuda_available"] = False

    logger.info("Evaluation complete: %s", result["status"])
    return result


def main() -> None:
    """Run endless worker cycle until shutdown signal is received."""
    _configure_logging()
    _register_signal_handlers()

    print("=" * 60)
    print("  S3M BACKGROUND WORKER")
    print(f"  Mode: {DEPLOYMENT_MODE}")
    print(f"  Device: {DEVICE}")
    print(f"  Interval: {WORKER_INTERVAL}s")
    print(f"  Checkpoint dir: {CHECKPOINT_DIR}")
    print(f"  Replay dir: {REPLAY_DIR}")
    print("=" * 60)

    if DEVICE != "cpu":
        try:
            import torch

            if torch.cuda.is_available():
                logger.info("CUDA detected: %s", torch.cuda.get_device_name(0))
            else:
                logger.info("CUDA unavailable; worker continues in CPU fallback")
        except ImportError:
            logger.info("PyTorch unavailable; worker continues in CPU fallback")
    else:
        logger.info("CPU mode enabled; skipping GPU-dependent operations")

    cycle_count = 0
    while not _shutdown_requested:
        cycle_count += 1
        logger.info("=== Worker cycle %d start ===", cycle_count)

        replay_files = _scan_replay_data()
        logger.info("Found %d unprocessed replay files", len(replay_files))

        if replay_files:
            cycle_result = _run_self_training_cycle(replay_files)
            logger.info("Training cycle status: %s", cycle_result.get("status"))

            checkpoint_path = _save_checkpoint(cycle_result)
            if checkpoint_path:
                eval_result = _run_evaluation(checkpoint_path)
                logger.info("Evaluation status: %s", eval_result.get("status"))
        else:
            logger.info("No replay data available; training step skipped")

        logger.info("=== Worker cycle %d done; sleeping %ds ===", cycle_count, WORKER_INTERVAL)
        for _ in range(WORKER_INTERVAL):
            if _shutdown_requested:
                break
            time.sleep(1)

    logger.info("Worker shutdown complete after %d cycles", cycle_count)


if __name__ == "__main__":
    main()
