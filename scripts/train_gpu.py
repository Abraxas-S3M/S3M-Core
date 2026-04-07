#!/usr/bin/env python3
"""S3M GPU Training Launcher — RunPod 4090 Fine-Tuning.

Usage:
  python scripts/train_gpu.py --engine phi3 --dataset data/datasets/s3m_tactical.jsonl
  python scripts/train_gpu.py --engine allam --dataset data/datasets/s3m_arabic.jsonl
  python scripts/train_gpu.py --engine grok --dataset data/datasets/s3m_reasoning.jsonl --gpus 2

Environment:
  WANDB_API_KEY=...      Enable Weights & Biases logging
  MLFLOW_TRACKING_URI=...  Enable MLflow tracking
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.training.gpu.config import GPUTrainingConfig
from src.training.gpu.lora_trainer import S3MLoRATrainer


def main() -> int:
    parser = argparse.ArgumentParser(description="S3M GPU LoRA Fine-Tuning")
    parser.add_argument("--engine", required=True, choices=["phi3", "mistral", "grok", "allam"],
                        help="S3M engine to fine-tune")
    parser.add_argument("--dataset", required=True, help="Path to JSONL dataset or HF dataset name")
    parser.add_argument("--config", default="configs/gpu_training.yaml", help="GPU training config path")
    parser.add_argument("--output-dir", default="checkpoints/gpu", help="Output directory for checkpoints")
    parser.add_argument("--resume-from", default=None, help="Resume from checkpoint path")
    parser.add_argument("--gpus", type=int, default=None, help="Override GPU count")
    parser.add_argument("--max-steps", type=int, default=None, help="Override max training steps")
    parser.add_argument("--run-name", default=None, help="Custom run name for tracking")
    args = parser.parse_args()

    logging.basicConfig(
        level=os.environ.get("S3M_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    config = GPUTrainingConfig.from_yaml(args.config)
    if args.max_steps:
        config.max_steps = args.max_steps

    trainer = S3MLoRATrainer(
        engine_id=args.engine,
        config=config,
        output_dir=args.output_dir,
        run_name=args.run_name,
    )

    metrics = trainer.train(
        dataset_path=args.dataset,
        resume_from=args.resume_from,
    )

    results_file = Path(args.output_dir) / f"{metrics['run_name']}_results.json"
    results_file.write_text(json.dumps(metrics, indent=2))
    print(f"\n{'='*60}")
    print(f"  S3M Training Complete: {args.engine}")
    print(f"  Adapter: {metrics['adapter_path']}")
    print(f"  Duration: {metrics['elapsed_seconds']}s")
    print(f"{'='*60}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
