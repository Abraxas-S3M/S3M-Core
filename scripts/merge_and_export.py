#!/usr/bin/env python3
"""S3M Merge & GGUF Export CLI.

Usage:
  python scripts/merge_and_export.py --engine phi3 --adapter checkpoints/gpu/s3m-phi3-*/final_adapter
  python scripts/merge_and_export.py --engine allam --adapter checkpoints/gpu/s3m-allam-*/final_adapter --quant Q4_K_M
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

from src.training.gpu.merge_and_export import ModelMerger


def main() -> int:
    parser = argparse.ArgumentParser(description="S3M Merge LoRA & Export GGUF")
    parser.add_argument("--engine", required=True, choices=["phi3", "mistral", "grok", "allam"])
    parser.add_argument("--adapter", required=True, help="Path to LoRA adapter directory")
    parser.add_argument("--base-model", default=None, help="Override base model HF repo")
    parser.add_argument("--quant", default="Q4_K_M", help="Quantization type")
    parser.add_argument("--llama-cpp", default="llama.cpp", help="Path to llama.cpp directory")
    parser.add_argument("--merge-only", action="store_true", help="Only merge, skip GGUF")
    parser.add_argument("--output-dir", default="models/merged")
    parser.add_argument("--gguf-dir", default="models/gguf")
    args = parser.parse_args()

    logging.basicConfig(level=os.environ.get("S3M_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s :: %(message)s")

    merger = ModelMerger(
        output_dir=args.output_dir,
        gguf_dir=args.gguf_dir,
        llama_cpp_path=args.llama_cpp,
    )

    if args.merge_only:
        result = merger.merge_adapter(args.engine, args.adapter, args.base_model)
    else:
        result = merger.full_pipeline(args.engine, args.adapter, args.base_model, args.quant)

    print(json.dumps({
        "engine": result.engine_id,
        "success": result.success,
        "merged_path": result.merged_path,
        "gguf_path": result.gguf_path,
        "sha256": result.sha256,
        "size_mb": round(result.size_bytes / (1024 * 1024), 1),
        "elapsed": result.elapsed_seconds,
        "error": result.error,
    }, indent=2))

    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
