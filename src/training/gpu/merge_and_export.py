"""S3M Model Merge & GGUF Export Pipeline.

Military/tactical context:
After LoRA fine-tuning on RunPod 4090s, adapters are merged into the base
model on Hetzner CPU nodes (which have more RAM), then quantized to GGUF
for deployment on Jetson AGX Orin or llama.cpp inference.

Pipeline:
  1. Merge LoRA adapter into base model (CPU, high RAM)
  2. Convert merged model to GGUF format
  3. Quantize to Q4_K_M for deployment
  4. Register in S3M model manifest
  5. Verify SHA-256 integrity
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("s3m.training.gpu.merge_and_export")

# ── Dependency gates ─────────────────────────────────────────────────────

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    MERGE_AVAILABLE = True
except ImportError:
    MERGE_AVAILABLE = False


# ── Engine → GGUF mapping (from scripts/model_pipeline/offline_model_ci.py) ──

ENGINE_GGUF_MAP = {
    "phi3": {
        "hf_repo": "microsoft/Phi-3-mini-4k-instruct",
        "gguf_name": "phi-3-mini-4k-instruct-s3m.Q4_K_M.gguf",
        "quant": "Q4_K_M",
    },
    "mistral": {
        "hf_repo": "mistralai/Mistral-7B-Instruct-v0.3",
        "gguf_name": "mistral-7b-instruct-v0.3-s3m.Q4_K_M.gguf",
        "quant": "Q4_K_M",
    },
    "grok": {
        "hf_repo": "xai-org/grok-1",
        "gguf_name": "grok-1-s3m.Q4_K_M.gguf",
        "quant": "Q4_K_M",
    },
    "allam": {
        "hf_repo": "sdaia/allam-7b",
        "gguf_name": "allam-7b-s3m.Q4_K_M.gguf",
        "quant": "Q4_K_M",
    },
}


@dataclass
class MergeResult:
    engine_id: str
    merged_path: str
    gguf_path: Optional[str]
    sha256: Optional[str]
    size_bytes: int
    elapsed_seconds: float
    success: bool
    error: Optional[str] = None


class ModelMerger:
    """Merge LoRA adapters and export to GGUF."""

    def __init__(
        self,
        output_dir: str = "models/merged",
        gguf_dir: str = "models/gguf",
        llama_cpp_path: str = "llama.cpp",
    ) -> None:
        self.output_dir = Path(output_dir)
        self.gguf_dir = Path(gguf_dir)
        self.llama_cpp_path = Path(llama_cpp_path)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.gguf_dir.mkdir(parents=True, exist_ok=True)

    def merge_adapter(
        self,
        engine_id: str,
        adapter_path: str,
        base_model: Optional[str] = None,
    ) -> MergeResult:
        """Merge LoRA adapter into base model (runs on CPU)."""
        if not MERGE_AVAILABLE:
            return MergeResult(
                engine_id=engine_id, merged_path="", gguf_path=None,
                sha256=None, size_bytes=0, elapsed_seconds=0, success=False,
                error="torch/transformers/peft not installed",
            )

        cfg = ENGINE_GGUF_MAP.get(engine_id)
        if not cfg:
            return MergeResult(
                engine_id=engine_id, merged_path="", gguf_path=None,
                sha256=None, size_bytes=0, elapsed_seconds=0, success=False,
                error=f"Unknown engine: {engine_id}",
            )

        hf_repo = base_model or cfg["hf_repo"]
        merged_path = self.output_dir / f"{engine_id}-s3m-merged"

        logger.info("Merging adapter for %s: base=%s adapter=%s", engine_id, hf_repo, adapter_path)
        t0 = time.perf_counter()

        try:
            # Load base model in float16 on CPU
            base = AutoModelForCausalLM.from_pretrained(
                hf_repo,
                torch_dtype=torch.float16,
                device_map="cpu",
                trust_remote_code=True,
            )
            tokenizer = AutoTokenizer.from_pretrained(hf_repo, trust_remote_code=True)

            # Load and merge adapter
            model = PeftModel.from_pretrained(base, adapter_path)
            model = model.merge_and_unload()

            # Save merged model
            model.save_pretrained(str(merged_path))
            tokenizer.save_pretrained(str(merged_path))

            elapsed = time.perf_counter() - t0
            size = sum(f.stat().st_size for f in merged_path.rglob("*") if f.is_file())

            logger.info("Merge complete: %s (%.1fs, %dMB)", merged_path, elapsed, size // (1024 * 1024))
            return MergeResult(
                engine_id=engine_id,
                merged_path=str(merged_path),
                gguf_path=None,
                sha256=None,
                size_bytes=size,
                elapsed_seconds=round(elapsed, 1),
                success=True,
            )

        except Exception as exc:
            elapsed = time.perf_counter() - t0
            logger.exception("Merge failed for %s", engine_id)
            return MergeResult(
                engine_id=engine_id, merged_path="", gguf_path=None,
                sha256=None, size_bytes=0, elapsed_seconds=round(elapsed, 1),
                success=False, error=str(exc),
            )

    def convert_to_gguf(
        self,
        engine_id: str,
        merged_path: str,
        quantization: str = "Q4_K_M",
    ) -> MergeResult:
        """Convert merged HF model to GGUF format using llama.cpp."""
        cfg = ENGINE_GGUF_MAP.get(engine_id, {})
        gguf_name = cfg.get("gguf_name", f"{engine_id}-s3m.{quantization}.gguf")
        gguf_fp16 = self.gguf_dir / f"{engine_id}-s3m-f16.gguf"
        gguf_quant = self.gguf_dir / gguf_name

        convert_script = self.llama_cpp_path / "convert_hf_to_gguf.py"
        quantize_bin = self.llama_cpp_path / "build" / "bin" / "llama-quantize"

        t0 = time.perf_counter()

        try:
            # Step 1: Convert to GGUF F16
            logger.info("Converting %s to GGUF F16", engine_id)
            subprocess.run(
                ["python", str(convert_script), merged_path, "--outfile", str(gguf_fp16), "--outtype", "f16"],
                check=True, capture_output=True, text=True,
            )

            # Step 2: Quantize
            logger.info("Quantizing to %s", quantization)
            subprocess.run(
                [str(quantize_bin), str(gguf_fp16), str(gguf_quant), quantization],
                check=True, capture_output=True, text=True,
            )

            # Cleanup F16 intermediate
            if gguf_fp16.exists() and gguf_quant.exists():
                gguf_fp16.unlink()

            # Compute SHA-256
            sha256 = self._sha256(gguf_quant)
            size = gguf_quant.stat().st_size
            elapsed = time.perf_counter() - t0

            logger.info("GGUF export complete: %s (%dMB, %.1fs)", gguf_quant, size // (1024 * 1024), elapsed)
            return MergeResult(
                engine_id=engine_id,
                merged_path=merged_path,
                gguf_path=str(gguf_quant),
                sha256=sha256,
                size_bytes=size,
                elapsed_seconds=round(elapsed, 1),
                success=True,
            )

        except Exception as exc:
            elapsed = time.perf_counter() - t0
            logger.exception("GGUF conversion failed for %s", engine_id)
            return MergeResult(
                engine_id=engine_id, merged_path=merged_path, gguf_path=None,
                sha256=None, size_bytes=0, elapsed_seconds=round(elapsed, 1),
                success=False, error=str(exc),
            )

    def full_pipeline(
        self,
        engine_id: str,
        adapter_path: str,
        base_model: Optional[str] = None,
        quantization: str = "Q4_K_M",
    ) -> MergeResult:
        """Run full merge → convert → quantize pipeline."""
        merge_result = self.merge_adapter(engine_id, adapter_path, base_model)
        if not merge_result.success:
            return merge_result

        return self.convert_to_gguf(engine_id, merge_result.merged_path, quantization)

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
