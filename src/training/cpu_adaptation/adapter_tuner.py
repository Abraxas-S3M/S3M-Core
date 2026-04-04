"""CPU-focused LoRA/QLoRA adapter tuning for austere edge retraining."""

from __future__ import annotations

import json
import logging
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import torch

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None  # type: ignore

try:
    from peft import LoraConfig, get_peft_model  # type: ignore

    PEFT_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    LoraConfig = None  # type: ignore
    get_peft_model = None  # type: ignore
    PEFT_AVAILABLE = False

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # type: ignore

    TRANSFORMERS_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    AutoModelForCausalLM = None  # type: ignore
    AutoTokenizer = None  # type: ignore
    BitsAndBytesConfig = None  # type: ignore
    TRANSFORMERS_AVAILABLE = False

try:
    import bitsandbytes as _bnb  # type: ignore

    _ = _bnb
    BNB_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    BNB_AVAILABLE = False


logger = logging.getLogger("s3m.training.adapter_tuner")


@dataclass
class AdapterConfig:
    """Configuration for LoRA adapter tuning on constrained CPU nodes."""

    lora_rank: int = 8
    lora_alpha: int = 16
    target_modules: list[str] = field(default_factory=lambda: ["q_proj", "v_proj"])
    learning_rate: float = 2e-4
    max_steps: int = 200
    batch_size: int = 1
    gradient_accumulation_steps: int = 4
    max_memory_mb: int = 4096


@dataclass
class TrainingResult:
    """Result metadata from edge adapter tuning."""

    loss_history: list[float]
    steps_completed: int
    peak_memory_mb: float
    duration_seconds: float
    adapter_path: str


class CPUAdapterTuner:
    """Fine-tunes LoRA adapters with strict CPU and memory constraints.

    Military/tactical context:
    This component is designed for comms-denied edge nodes where only CPU cycles
    are reliably available. It keeps adaptation local to preserve mission
    sovereignty and enables small-sample updates without cloud dependency.
    """

    def __init__(self, base_model_path: str, adapter_config: AdapterConfig) -> None:
        if not isinstance(base_model_path, str) or not base_model_path.strip():
            raise ValueError("base_model_path must be a non-empty string")
        self.base_model_path = base_model_path
        self.adapter_config = adapter_config
        self._model: Any = None
        self._tokenizer: Any = None
        self._lora_config: Any = None
        self._prepared = False
        self._backend = "uninitialized"
        self._last_adapter_path = ""

    def _current_rss_mb(self) -> float:
        if psutil is not None:
            process = psutil.Process(os.getpid())
            return float(process.memory_info().rss) / (1024.0 * 1024.0)

        usage_kb = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform == "darwin":
            return usage_kb / (1024.0 * 1024.0)
        return usage_kb / 1024.0

    def _enforce_memory_budget(self) -> float:
        current_mb = self._current_rss_mb()
        if current_mb > float(self.adapter_config.max_memory_mb):
            raise MemoryError(
                f"Memory budget exceeded: RSS={current_mb:.2f}MB > "
                f"{self.adapter_config.max_memory_mb}MB"
            )
        return current_mb

    def _validate_dataset(self, dataset: list[dict]) -> None:
        if not isinstance(dataset, list) or not dataset:
            raise ValueError("dataset must be a non-empty list")
        required = {"instruction", "input", "output"}
        for idx, row in enumerate(dataset):
            if not isinstance(row, dict):
                raise ValueError(f"dataset item at index {idx} must be a dict")
            if not required.issubset(row.keys()):
                raise ValueError(f"dataset item at index {idx} missing required keys: {required}")
            for key in required:
                if not isinstance(row[key], str):
                    raise ValueError(f"dataset item at index {idx} key '{key}' must be a string")

    @staticmethod
    def _format_sample(sample: dict[str, str]) -> str:
        return (
            "### Instruction:\n"
            f"{sample.get('instruction', '').strip()}\n\n"
            "### Input:\n"
            f"{sample.get('input', '').strip()}\n\n"
            "### Response:\n"
            f"{sample.get('output', '').strip()}"
        )

    def prepare(self) -> bool:
        """Load base model and initialize LoRA configuration for CPU training."""
        self._enforce_memory_budget()

        if not PEFT_AVAILABLE or LoraConfig is None:
            logger.error("peft is required for adapter tuning but is unavailable")
            return False

        self._lora_config = LoraConfig(
            r=int(self.adapter_config.lora_rank),
            lora_alpha=int(self.adapter_config.lora_alpha),
            target_modules=list(self.adapter_config.target_modules),
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
        )

        base_path = Path(self.base_model_path)
        if base_path.suffix.lower() in {".gguf", ".ggml"} and base_path.exists():
            self._prepared = True
            self._backend = "ggml"
            logger.info("Prepared GGML/GGUF adapter workflow for %s", self.base_model_path)
            return True

        if not TRANSFORMERS_AVAILABLE or AutoModelForCausalLM is None or AutoTokenizer is None:
            logger.error("transformers is required for HF adapter tuning but is unavailable")
            return False

        quantization_config = None
        if BNB_AVAILABLE and BitsAndBytesConfig is not None:
            try:
                quantization_config = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_compute_dtype=torch.float32,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("4-bit quantization config setup failed: %s", exc)
                quantization_config = None

        kwargs: dict[str, Any] = {
            "device_map": {"": "cpu"},
            "low_cpu_mem_usage": True,
        }
        if quantization_config is not None:
            kwargs["quantization_config"] = quantization_config

        try:
            self._model = AutoModelForCausalLM.from_pretrained(self.base_model_path, **kwargs)
        except Exception as exc:
            if "quantization_config" in kwargs:
                logger.warning("4-bit load failed (%s); retrying without bitsandbytes", exc)
                kwargs.pop("quantization_config", None)
                self._model = AutoModelForCausalLM.from_pretrained(self.base_model_path, **kwargs)
            else:
                logger.error("Failed to load base model from %s: %s", self.base_model_path, exc)
                return False

        self._tokenizer = AutoTokenizer.from_pretrained(self.base_model_path, use_fast=True)
        if self._tokenizer.pad_token_id is None and self._tokenizer.eos_token_id is not None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        if hasattr(self._model, "gradient_checkpointing_enable"):
            self._model.gradient_checkpointing_enable()
        if getattr(self._model, "config", None) is not None:
            self._model.config.use_cache = False

        self._model = get_peft_model(self._model, self._lora_config)
        self._model.to(torch.device("cpu"))
        self._prepared = True
        self._backend = "transformers"
        logger.info("CPU adapter tuner prepared for model: %s", self.base_model_path)
        return True

    def train(self, dataset: list[dict]) -> TrainingResult:
        """Run CPU LoRA adaptation loop with strict memory enforcement."""
        if not self._prepared and not self.prepare():
            raise RuntimeError("CPUAdapterTuner.prepare() failed")

        self._validate_dataset(dataset)
        if self._backend != "transformers" or self._model is None or self._tokenizer is None:
            raise RuntimeError(
                "Training backend is not fully initialized. "
                "GGML/GGUF mode supports export/merge workflows, not gradient updates."
            )

        self._model.train()
        optimizer = torch.optim.AdamW(self._model.parameters(), lr=float(self.adapter_config.learning_rate))
        grad_accum = max(1, int(self.adapter_config.gradient_accumulation_steps))
        batch_size = max(1, int(self.adapter_config.batch_size))

        losses: list[float] = []
        steps_completed = 0
        peak_memory_mb = self._enforce_memory_budget()
        start = time.perf_counter()
        cursor = 0

        for step in range(max(1, int(self.adapter_config.max_steps))):
            batch_rows = []
            for _ in range(batch_size):
                batch_rows.append(dataset[cursor % len(dataset)])
                cursor += 1
            texts = [self._format_sample(row) for row in batch_rows]

            enc = self._tokenizer(
                texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=1024,
            )
            input_ids = enc["input_ids"].to(torch.device("cpu"))
            attention_mask = enc.get("attention_mask", torch.ones_like(input_ids)).to(torch.device("cpu"))

            out = self._model(input_ids=input_ids, attention_mask=attention_mask, labels=input_ids)
            raw_loss = out.loss
            scaled_loss = raw_loss / grad_accum
            scaled_loss.backward()

            if ((step + 1) % grad_accum == 0) or (step + 1 == int(self.adapter_config.max_steps)):
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)

            loss_value = float(raw_loss.detach().cpu().item())
            losses.append(loss_value)
            steps_completed = step + 1

            current_mb = self._enforce_memory_budget()
            if current_mb > peak_memory_mb:
                peak_memory_mb = current_mb

        duration = time.perf_counter() - start
        if not self._last_adapter_path:
            temp_dir = tempfile.mkdtemp(prefix="s3m_adapter_")
            self.export_adapter(temp_dir)

        return TrainingResult(
            loss_history=losses,
            steps_completed=steps_completed,
            peak_memory_mb=peak_memory_mb,
            duration_seconds=duration,
            adapter_path=self._last_adapter_path,
        )

    def export_adapter(self, output_path: str) -> str:
        """Persist adapter weights/configuration and return export path."""
        if not isinstance(output_path, str) or not output_path.strip():
            raise ValueError("output_path must be a non-empty string")

        out_dir = Path(output_path)
        out_dir.mkdir(parents=True, exist_ok=True)

        if self._backend == "ggml":
            metadata = {
                "backend": "ggml_placeholder",
                "base_model_path": self.base_model_path,
                "adapter_config": asdict(self.adapter_config),
            }
            (out_dir / "adapter_metadata.json").write_text(
                json.dumps(metadata, indent=2),
                encoding="utf-8",
            )
            self._last_adapter_path = str(out_dir)
            return self._last_adapter_path

        if self._model is None:
            raise RuntimeError("Adapter model is not initialized; call prepare() first")

        self._model.save_pretrained(str(out_dir))
        if self._tokenizer is not None and hasattr(self._tokenizer, "save_pretrained"):
            self._tokenizer.save_pretrained(str(out_dir))
        self._last_adapter_path = str(out_dir)
        return self._last_adapter_path

    @staticmethod
    def _find_llamacpp_convert_script() -> Path | None:
        env_override = os.getenv("LLAMA_CPP_CONVERT")
        if env_override:
            candidate = Path(env_override)
            if candidate.exists():
                return candidate

        candidates = [
            Path.cwd() / "llama.cpp" / "convert.py",
            Path.cwd() / "third_party" / "llama.cpp" / "convert.py",
            Path("/opt/llama.cpp/convert.py"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def merge_and_quantize(self, output_path: str, quant_format: str = "q4_k_m") -> str:
        """Merge adapter into base model and attempt GGUF re-quantization."""
        if not isinstance(output_path, str) or not output_path.strip():
            raise ValueError("output_path must be a non-empty string")
        if not isinstance(quant_format, str) or not quant_format.strip():
            raise ValueError("quant_format must be a non-empty string")

        if self._backend == "ggml":
            source = Path(self.base_model_path)
            if not source.exists():
                raise FileNotFoundError(f"GGML/GGUF base model not found: {source}")
            target = Path(output_path)
            if target.suffix.lower() not in {".gguf", ".ggml"}:
                target.mkdir(parents=True, exist_ok=True)
                target = target / f"merged-{quant_format}.gguf"
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            return str(target)

        if self._model is None:
            raise RuntimeError("No adapter model available; call prepare() before merge")

        merged_model = self._model
        if hasattr(self._model, "merge_and_unload"):
            merged_model = self._model.merge_and_unload()

        merged_dir = Path(tempfile.mkdtemp(prefix="s3m_merged_model_"))
        merged_model.save_pretrained(str(merged_dir))
        if self._tokenizer is not None and hasattr(self._tokenizer, "save_pretrained"):
            self._tokenizer.save_pretrained(str(merged_dir))

        convert_script = self._find_llamacpp_convert_script()
        if convert_script is not None:
            gguf_target = Path(output_path)
            if gguf_target.suffix.lower() not in {".gguf", ".ggml"}:
                gguf_target.mkdir(parents=True, exist_ok=True)
                gguf_target = gguf_target / f"model-{quant_format}.gguf"
            else:
                gguf_target.parent.mkdir(parents=True, exist_ok=True)

            cmd = [
                sys.executable,
                str(convert_script),
                str(merged_dir),
                "--outfile",
                str(gguf_target),
                "--outtype",
                quant_format,
            ]
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if proc.returncode == 0 and gguf_target.exists():
                return str(gguf_target)
            logger.warning("llama.cpp conversion failed (%s): %s", proc.returncode, proc.stderr.strip())

        fallback_dir = Path(output_path)
        if fallback_dir.suffix:
            fallback_dir = fallback_dir.with_suffix("")
        fallback_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(merged_dir, fallback_dir, dirs_exist_ok=True)
        return str(fallback_dir)
