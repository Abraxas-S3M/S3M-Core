#!/usr/bin/env python3
"""S3M GPU Worker — Runs on RunPod, polls job queue, executes training.

Usage (on RunPod pod):
  python scripts/gpu_worker.py --poll-interval 30
  S3M_HETZNER_HOST=1.2.3.4 python scripts/gpu_worker.py
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.training.gpu.hybrid_orchestrator import HybridOrchestrator

logger = logging.getLogger("s3m.gpu_worker")

_shutdown = False


def _handle_signal(signum, _):
    global _shutdown
    _shutdown = True
    logger.warning("Signal %s received; shutting down GPU worker", signum)


def main() -> int:
    parser = argparse.ArgumentParser(description="S3M GPU Training Worker")
    parser.add_argument("--poll-interval", type=int, default=30, help="Seconds between queue polls")
    parser.add_argument("--queue-dir", default="state/training/job_queue")
    parser.add_argument("--one-shot", action="store_true", help="Run one job and exit")
    args = parser.parse_args()

    logging.basicConfig(level=os.environ.get("S3M_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s :: %(message)s")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    orchestrator = HybridOrchestrator(queue_dir=args.queue_dir, mode="gpu")
    logger.info("S3M GPU Worker started (poll=%ds)", args.poll_interval)

    while not _shutdown:
        result = orchestrator.gpu_poll_and_run()
        if result:
            logger.info("Job result: %s", result)
            if args.one_shot:
                return 0
        else:
            logger.debug("No pending jobs; sleeping %ds", args.poll_interval)
        time.sleep(args.poll_interval)

    logger.info("GPU Worker stopped cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
