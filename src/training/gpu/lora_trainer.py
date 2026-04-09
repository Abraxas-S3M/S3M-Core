"""S3M LoRA/QLoRA Fine-Tuning Trainer for RunPod 4090 GPUs.

Military/tactical context:
This trainer runs on cloud GPU pods and produces LoRA adapters for each
S3M engine. Adapters are lightweight (~50-200MB) and can be synced back
to Hetzner CPU nodes for merge and GGUF conversion.

Supports:
  - QLoRA 4-bit via bitsandbytes NF4
  - Unsloth 2× acceleration (when installed)
  - Flash Attention 2 (auto-detected)
  - Gradient checkpointing for VRAM efficiency
  - WandB / MLflow experiment tracking
  - Checkpoint resume from Hetzner-synced state
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("s3m.training.gpu.lora_trainer")

# ── Dependency gates ─────────────────────────────────────────────────────

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False

try:
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        TrainingArguments,
        BitsAndBytesConfig,
        TrainerCallback,
    )
    from peft import LoraConfig as PeftLoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
    from trl import SFTTrainer
    from datasets import load_dataset, Dataset
    HF_STACK_AVAILABLE = True
except ImportError:
    HF_STACK_AVAILABLE = False
    TrainerCallback = object  # type: ignore[assignment,misc]

try:
    from unsloth import FastLanguageModel
    UNSLOTH_AVAILABLE = True
except ImportError:
    UNSLOTH_AVAILABLE = False

from src.training.gpu.config import GPUTrainingConfig, EngineTrainingConfig


# ── S3M Dataset Formatter ────────────────────────────────────────────────

S3M_CHAT_TEMPLATE = """### System:
You are S3M, a sovereign military AI assistant for the Saudi Armed Forces.
Respond in the language of the query. For Arabic queries, respond in Arabic.

### Human:
{prompt}

### Assistant:
{completion}"""

S3M_ARABIC_TEMPLATE = """### النظام:
أنت S3M، مساعد ذكاء اصطناعي عسكري سيادي للقوات المسلحة السعودية.

### المستخدم:
{prompt}

### المساعد:
{completion}"""


def format_s3m_example(example: Dict[str, str], engine_id: str = "") -> str:
    """Format a training example into the S3M chat template."""
    prompt = example.get("prompt", example.get("instruction", ""))
    completion = example.get("completion", example.get("output", ""))

    # Use Arabic template for ALLaM when content is Arabic
    if engine_id == "allam" and any(
        "\u0600" <= ch <= "\u06FF" for ch in prompt[:100]
    ):
        return S3M_ARABIC_TEMPLATE.format(prompt=prompt, completion=completion)
    return S3M_CHAT_TEMPLATE.format(prompt=prompt, completion=completion)


# ── Core Trainer ─────────────────────────────────────────────────────────

class RuntimeLimitCallback(TrainerCallback):
    """Stops training when a hard runtime budget is reached."""

    def __init__(self, max_runtime_seconds: float) -> None:
        self.max_runtime_seconds = max_runtime_seconds
        self._start_time = 0.0
        self.time_limit_reached = False

    def on_train_begin(self, args, state, control, **kwargs):  # type: ignore[override]
        self._start_time = time.perf_counter()
        return control

    def on_step_end(self, args, state, control, **kwargs):  # type: ignore[override]
        elapsed = time.perf_counter() - self._start_time
        if elapsed >= self.max_runtime_seconds:
            self.time_limit_reached = True
            control.should_training_stop = True
        return control


class S3MLoRATrainer:
    """Fine-tune any S3M engine with QLoRA on RunPod 4090 GPUs."""

    def __init__(
        self,
        engine_id: str,
        config: Optional[GPUTrainingConfig] = None,
        output_dir: str = "checkpoints/gpu",
        run_name: Optional[str] = None,
    ) -> None:
        if not HF_STACK_AVAILABLE:
            raise RuntimeError(
                "GPU training requires: transformers, peft, trl, bitsandbytes, datasets. "
                "Install with: pip install -r requirements-gpu-training.txt"
            )

        self.config = config or GPUTrainingConfig.from_yaml()
        self.engine_id = engine_id
        self.engine_cfg = self.config.engines.get(engine_id)
        if not self.engine_cfg:
            raise ValueError(
                f"Engine '{engine_id}' not found in gpu_training.yaml. "
                f"Available: {list(self.config.engines.keys())}"
            )

        self.run_name = run_name or f"s3m-{engine_id}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"
        self.output_dir = Path(output_dir) / self.run_name
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.model = None
        self.tokenizer = None
        self.trainer = None

    def load_model(self) -> None:
        """Load base model with QLoRA quantization or Unsloth acceleration."""
        hf_repo = self.engine_cfg.hf_repo
        max_seq = self.engine_cfg.max_seq_length

        if self.config.unsloth_enabled and UNSLOTH_AVAILABLE:
            logger.info("Loading %s via Unsloth (2× faster LoRA)", hf_repo)
            self.model, self.tokenizer = FastLanguageModel.from_pretrained(
                model_name=hf_repo,
                max_seq_length=max_seq,
                load_in_4bit=self.config.quant.load_in_4bit,
                dtype=None,  # auto-detect
            )
            self.model = FastLanguageModel.get_peft_model(
                self.model,
                r=self.engine_cfg.lora_rank,
                lora_alpha=self.config.lora.alpha,
                lora_dropout=self.config.lora.dropout,
                target_modules=self.config.lora.target_modules,
                bias=self.config.lora.bias,
                use_gradient_checkpointing="unsloth",
                max_seq_length=max_seq,
            )
        else:
            logger.info("Loading %s via standard HF + bitsandbytes QLoRA", hf_repo)
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=self.config.quant.load_in_4bit,
                bnb_4bit_compute_dtype=getattr(torch, self.config.quant.bnb_4bit_compute_dtype, torch.bfloat16),
                bnb_4bit_quant_type=self.config.quant.bnb_4bit_quant_type,
                bnb_4bit_use_double_quant=self.config.quant.bnb_4bit_use_double_quant,
            )

            self.model = AutoModelForCausalLM.from_pretrained(
                hf_repo,
                quantization_config=bnb_config,
                device_map="auto",
                trust_remote_code=True,
                attn_implementation="flash_attention_2" if self._has_flash_attn() else "sdpa",
            )
            self.model = prepare_model_for_kbit_training(self.model)

            peft_config = PeftLoraConfig(
                r=self.engine_cfg.lora_rank,
                lora_alpha=self.config.lora.alpha,
                lora_dropout=self.config.lora.dropout,
                target_modules=self.config.lora.target_modules,
                bias=self.config.lora.bias,
                task_type=TaskType.CAUSAL_LM,
            )
            self.model = get_peft_model(self.model, peft_config)

            self.tokenizer = AutoTokenizer.from_pretrained(
                hf_repo,
                trust_remote_code=True,
                **self.engine_cfg.tokenizer_kwargs,
            )

        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id

        trainable = sum(p.numel() for p in self.model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in self.model.parameters())
        logger.info(
            "Model loaded: %s | Trainable: %s / %s (%.2f%%)",
            hf_repo, f"{trainable:,}", f"{total:,}", 100 * trainable / max(1, total),
        )

    def prepare_dataset(self, dataset_path: str) -> Dataset:
        """Load and format dataset for SFT training."""
        path = Path(dataset_path)

        if path.suffix == ".jsonl" or path.suffix == ".json":
            ds = load_dataset("json", data_files=str(path), split="train")
        elif path.is_dir():
            ds = load_dataset(str(path), split="train")
        else:
            # Try loading from HuggingFace hub
            ds = load_dataset(dataset_path, split="train")

        logger.info("Dataset loaded: %d examples from %s", len(ds), dataset_path)
        return ds

    def train(
        self,
        dataset_path: str,
        resume_from: Optional[str] = None,
        max_runtime_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Run LoRA fine-tuning and return metrics."""
        if self.model is None:
            self.load_model()

        dataset = self.prepare_dataset(dataset_path)

        # Configure WandB if available
        report_to = []
        if os.environ.get("WANDB_API_KEY"):
            report_to.append("wandb")
            os.environ.setdefault("WANDB_PROJECT", f"s3m-{self.engine_id}")
        if os.environ.get("MLFLOW_TRACKING_URI"):
            report_to.append("mlflow")

        training_args = TrainingArguments(
            output_dir=str(self.output_dir),
            run_name=self.run_name,
            max_steps=self.config.max_steps,
            per_device_train_batch_size=self.config.per_device_batch_size,
            gradient_accumulation_steps=self.config.gradient_accumulation_steps,
            learning_rate=self.config.learning_rate,
            weight_decay=0.01,
            warmup_ratio=0.03,
            lr_scheduler_type="cosine",
            bf16=self.config.bf16,
            tf32=True,
            gradient_checkpointing=self.config.gradient_checkpointing,
            logging_steps=10,
            save_steps=200,
            eval_steps=200,
            save_total_limit=3,
            report_to=report_to if report_to else "none",
            optim="paged_adamw_8bit",
            seed=42,
            dataloader_num_workers=4,
            remove_unused_columns=False,
        )

        def formatting_func(examples):
            texts = []
            for i in range(len(examples.get("prompt", examples.get("instruction", [])))):
                ex = {k: v[i] for k, v in examples.items()}
                texts.append(format_s3m_example(ex, self.engine_id))
            return texts

        runtime_callback = None
        if max_runtime_seconds and max_runtime_seconds > 0:
            runtime_callback = RuntimeLimitCallback(max_runtime_seconds=max_runtime_seconds)

        trainer = SFTTrainer(
            model=self.model,
            tokenizer=self.tokenizer,
            train_dataset=dataset,
            args=training_args,
            formatting_func=formatting_func,
            max_seq_length=self.engine_cfg.max_seq_length,
            packing=True,
            callbacks=[runtime_callback] if runtime_callback else None,
        )

        logger.info("Starting training: %s | steps=%d", self.run_name, self.config.max_steps)
        t0 = time.perf_counter()

        if resume_from:
            trainer.train(resume_from_checkpoint=resume_from)
        else:
            trainer.train()

        elapsed = time.perf_counter() - t0
        logger.info("Training complete in %.1fs", elapsed)

        time_limit_reached = bool(runtime_callback and runtime_callback.time_limit_reached)
        checkpoint_path: Optional[Path] = None
        if time_limit_reached:
            checkpoint_path = self.output_dir / "time_limit_checkpoint"
            trainer.save_model(str(checkpoint_path))
            trainer.save_state()
            logger.warning("Session time limit reached. Checkpoint saved for resume.")

        # Save final adapter
        adapter_path = self.output_dir / "final_adapter"
        self.model.save_pretrained(str(adapter_path))
        self.tokenizer.save_pretrained(str(adapter_path))

        final_loss = None
        for entry in reversed(trainer.state.log_history):
            if "loss" in entry:
                final_loss = float(entry["loss"])
                break

        examples_processed = (
            int(trainer.state.global_step)
            * int(self.config.per_device_batch_size)
            * int(self.config.gradient_accumulation_steps)
        )
        training_completed = bool(trainer.state.global_step >= self.config.max_steps and not time_limit_reached)

        metrics = {
            "engine_id": self.engine_id,
            "run_name": self.run_name,
            "hf_repo": self.engine_cfg.hf_repo,
            "lora_rank": self.engine_cfg.lora_rank,
            "steps": self.config.max_steps,
            "global_step": int(trainer.state.global_step),
            "elapsed_seconds": round(elapsed, 1),
            "final_loss": final_loss,
            "examples_processed": examples_processed,
            "training_completed": training_completed,
            "time_limit_reached": time_limit_reached,
            "checkpoint_path": str(checkpoint_path) if checkpoint_path else None,
            "adapter_path": str(adapter_path),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("Adapter saved: %s", adapter_path)
        return metrics

    @staticmethod
    def _has_flash_attn() -> bool:
        try:
            import flash_attn
            return True
        except ImportError:
            return False
