#!/usr/bin/env python3
"""
S3M UNCLASSIFIED - FOUO
Tactical context: this QLoRA path produces compact adapters that can be rapidly
transported and merged in disconnected military edge environments.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)


@dataclass(frozen=True)
class EngineConfig:
    model_id: str
    engine_id: str
    lora_r: int
    lora_alpha: int
    batch_size: int


ENGINE_CONFIGS: dict[str, EngineConfig] = {
    "phi3_medium": EngineConfig(
        model_id="microsoft/Phi-3-medium-4k-instruct",
        engine_id="phi3-medium",
        lora_r=16,
        lora_alpha=32,
        batch_size=4,
    ),
    "allam": EngineConfig(
        model_id="humain-ai/ALLaM-7B-Instruct-preview",
        engine_id="allam",
        lora_r=16,
        lora_alpha=32,
        batch_size=8,
    ),
    "mixtral": EngineConfig(
        model_id="mistralai/Mixtral-8x7B-Instruct-v0.1",
        engine_id="mixtral",
        lora_r=8,
        lora_alpha=16,
        batch_size=2,
    ),
}

DATASET_PATH = Path("/workspace/datasets/train.jsonl")
OUTPUT_ROOT = Path("/workspace/output/adapters")
LOCAL_BASE_ROOT = Path("/workspace/base_weights")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run QLoRA finetuning for S3M engines.")
    parser.add_argument(
        "--engine",
        required=True,
        choices=["phi3_medium", "allam", "mixtral", "grok1"],
        help="Target engine to finetune. grok1 is explicitly unsupported in this script.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Upload trained adapters to Object Storage vault after training finishes.",
    )
    parser.add_argument(
        "--track",
        default="saudi_mod",
        help="Training track label used for adapter storage placement.",
    )
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-length", type=int, default=2048)
    return parser.parse_args()


def validate_engine(engine: str) -> EngineConfig:
    if engine == "grok1":
        print("ERROR: grok1 is not supported by qlora_finetune.py. Use a dedicated pipeline.", file=sys.stderr)
        raise SystemExit(2)
    return ENGINE_CONFIGS[engine]


def resolve_model_source(cfg: EngineConfig) -> str:
    local_dir = LOCAL_BASE_ROOT / cfg.engine_id
    if local_dir.exists() and any(local_dir.iterdir()):
        return str(local_dir)
    return cfg.model_id


def resolve_text_field(column_names: list[str]) -> str:
    for candidate in ("text", "prompt", "instruction", "content"):
        if candidate in column_names:
            return candidate
    raise ValueError(f"Dataset must include one of ['text','prompt','instruction','content']; got: {column_names}")


def maybe_push_to_vault(output_dir: Path, engine_id: str, track: str = "saudi_mod") -> None:
    """Push trained LoRA adapter to Hetzner Object Storage vault."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.storage.b2_connector import B2Connector
    from src.storage.vault_paths import VaultPaths

    connector = B2Connector()
    remote_prefix = VaultPaths.fp16_adapter(engine_id, track)
    result = connector.sync_up(output_dir, remote_prefix)
    uploaded = len(result) if isinstance(result, list) else int(result.get("uploaded", 0))
    print(f"Adapter pushed to Object Storage: {remote_prefix}")
    print(f"  Files uploaded: {uploaded}")


def main() -> int:
    args = parse_args()
    cfg = validate_engine(args.engine)

    if args.engine == "mixtral":
        print("NOTE: mixtral QLoRA commonly needs 2x RTX 4090 for stable throughput.", flush=True)

    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    model_source = resolve_model_source(cfg)
    output_dir = OUTPUT_ROOT / args.engine
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset = load_dataset("json", data_files=str(DATASET_PATH), split="train")
    text_field = resolve_text_field(dataset.column_names)

    tokenizer = AutoTokenizer.from_pretrained(model_source, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    def tokenize_batch(batch: dict[str, list[str]]) -> dict[str, list[list[int]]]:
        return tokenizer(
            batch[text_field],
            truncation=True,
            max_length=args.max_length,
            padding=False,
        )

    tokenized_dataset = dataset.map(tokenize_batch, batched=True, remove_columns=dataset.column_names)

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_source,
        quantization_config=bnb_config,
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
        device_map="auto",
    )
    model = prepare_model_for_kbit_training(model)

    lora_cfg = LoraConfig(
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_cfg)

    train_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=cfg.batch_size,
        gradient_accumulation_steps=4,
        learning_rate=args.lr,
        bf16=True,
        logging_steps=10,
        save_strategy="epoch",
        report_to="none",
        remove_unused_columns=False,
    )

    trainer = Trainer(
        model=model,
        args=train_args,
        train_dataset=tokenized_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )
    trainer.train()

    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    print(f"Adapter saved to: {output_dir}")

    if args.push:
        maybe_push_to_vault(output_dir, cfg.engine_id, args.track)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
