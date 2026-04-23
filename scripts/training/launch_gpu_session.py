#!/usr/bin/env python3
"""Launch a bounded RunPod GPU training session for S3M.

Military/tactical context:
This launcher executes a single controlled training sortie window, ensuring the
adapter and checkpoint intelligence are returned to sovereign storage before the
leased GPU pod is released.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from typing import Optional, Sequence, Type

from src.training.gpu.session_manager import GPUSessionManager, GrokTrainingBlockedError

logger = logging.getLogger("s3m.training.gpu.launch_gpu_session")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run full RunPod GPU session lifecycle for S3M QLoRA training.",
    )
    parser.add_argument(
        "--engine",
        required=True,
        help="Engine target (e.g. phi3-medium or mistral-7b).",
    )
    parser.add_argument(
        "--track",
        required=True,
        choices=["saudi_mod", "ukraine_mod", "nato", "indopac_mod", "southam_mod", "africa_mod"],
        help="Training data track.",
    )
    parser.add_argument(
        "--max-hours",
        type=float,
        default=4.0,
        help="Hard session runtime cap in hours (default: 4.0).",
    )
    parser.add_argument(
        "--dataset-override",
        default=None,
        help="Optional local dataset path override.",
    )
    parser.add_argument(
        "--config",
        default="configs/gpu_training.yaml",
        help="GPU training config path.",
    )
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    manager_cls: Type[GPUSessionManager] = GPUSessionManager,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    try:
        manager = manager_cls(config_path=args.config)
        result = manager.launch_session(
            engine_id=args.engine,
            track=args.track,
            max_runtime_hours=args.max_hours,
            dataset_override=args.dataset_override,
        )
    except GrokTrainingBlockedError as exc:
        print(f'ERROR: "{exc}"', file=sys.stderr)
        return 2
    except Exception as exc:
        logger.exception("GPU session launch failed.")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(asdict(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

