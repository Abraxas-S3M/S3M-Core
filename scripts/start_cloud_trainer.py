#!/usr/bin/env python3
"""Start S3M cloud CPU trainer orchestration.

Military/tactical context:
The launcher keeps adaptation active for one or multiple doctrine tracks while
allowing clean shutdown on SIGTERM/SIGINT so checkpoint integrity is preserved
during container restarts or controlled redeployments.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from typing import List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from src.training.cloud_cpu.paths import StatePaths, TrainingTrack
except Exception:  # pragma: no cover - fallback when chunk paths are not installed yet
    from src.training.cloud_cpu.trainer_service import StatePaths, TrainingTrack

from src.training.cloud_cpu.trainer_service import TrainerService

logger = logging.getLogger("s3m.training.start_cloud_trainer")

_shutdown = False
_services: List[TrainerService] = []


def _handle_signal(signum: int, _frame: object) -> None:
    global _shutdown
    _shutdown = True
    logger.warning("Signal %s received; stopping trainer services", signum)
    for service in list(_services):
        service.stop()


def _setup_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("S3M_TRAINER_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


def _select_tracks(track_env: str) -> list[TrainingTrack]:
    if track_env:
        return [TrainingTrack(track_env.strip())]
    return [track for track in TrainingTrack]


def main() -> int:
    _setup_logging()
    deployment_mode = os.environ.get("DEPLOYMENT_MODE", "cloud_cpu_demo").strip()
    track_env = os.environ.get("S3M_TRAINING_TRACK", "").strip()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info("Starting cloud trainer launcher (mode=%s track=%s)", deployment_mode, track_env or "all")

    try:
        tracks = _select_tracks(track_env)
    except ValueError:
        logger.error("Unknown S3M_TRAINING_TRACK=%s", track_env)
        return 1

    paths = StatePaths()
    paths.ensure_dirs()

    for track in tracks:
        _services.append(TrainerService(track=track, paths=paths))

    if len(_services) == 1:
        _services[0].start()
        return 0

    # Round-robin operation across all tracks when no explicit single-track is set.
    track_index = 0
    while not _shutdown:
        service = _services[track_index % len(_services)]
        track_index += 1
        try:
            service.run_cycle_once()
        except Exception:  # pragma: no cover - launcher guard
            logger.exception("Trainer cycle failed for track=%s", service.get_status().get("track"))
            time.sleep(2.0)
        if not _shutdown:
            time.sleep(0.5)

    logger.info("Cloud trainer launcher stopped cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
