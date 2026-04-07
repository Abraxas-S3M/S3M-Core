"""S3M GPU Training Configuration Loader.

Loads configs/gpu_training.yaml and provides typed access to all
training hyperparameters, engine overrides, and hybrid settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class LoRAConfig:
    rank: int = 16
    alpha: int = 32
    dropout: float = 0.05
    target_modules: List[str] = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ])
    bias: str = "none"
    task_type: str = "CAUSAL_LM"


@dataclass
class QuantConfig:
    load_in_4bit: bool = True
    bnb_4bit_compute_dtype: str = "bfloat16"
    bnb_4bit_quant_type: str = "nf4"
    bnb_4bit_use_double_quant: bool = True


@dataclass
class EngineTrainingConfig:
    engine_id: str
    hf_repo: str
    lora_rank: int = 16
    gpus_required: int = 1
    strategy: str = "single_gpu"
    max_seq_length: int = 4096
    dataset: str = "s3m_default_instruct"
    tokenizer_kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GPUTrainingConfig:
    lora: LoRAConfig = field(default_factory=LoRAConfig)
    quant: QuantConfig = field(default_factory=QuantConfig)
    engines: Dict[str, EngineTrainingConfig] = field(default_factory=dict)
    max_steps: int = 2000
    learning_rate: float = 2e-4
    per_device_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    bf16: bool = True
    gradient_checkpointing: bool = True
    unsloth_enabled: bool = True

    @classmethod
    def from_yaml(cls, path: str = "configs/gpu_training.yaml") -> "GPUTrainingConfig":
        config_path = Path(path)
        if not config_path.exists():
            return cls()
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return cls()

        lora_raw = raw.get("training", {}).get("lora", {})
        quant_raw = raw.get("training", {}).get("quantization", {})
        engines_raw = raw.get("engines", {})

        lora = LoRAConfig(**{k: v for k, v in lora_raw.items() if k in LoRAConfig.__dataclass_fields__})
        quant = QuantConfig(**{k: v for k, v in quant_raw.items() if k in QuantConfig.__dataclass_fields__})

        engines = {}
        for eid, ecfg in engines_raw.items():
            engines[eid] = EngineTrainingConfig(
                engine_id=eid,
                hf_repo=ecfg.get("hf_repo", ""),
                lora_rank=ecfg.get("lora_rank", lora.rank),
                gpus_required=ecfg.get("gpus_required", 1),
                strategy=ecfg.get("strategy", "single_gpu"),
                max_seq_length=ecfg.get("max_seq_length", 4096),
                dataset=ecfg.get("dataset", "s3m_default_instruct"),
                tokenizer_kwargs=ecfg.get("tokenizer_kwargs", {}),
            )

        training = raw.get("training", {})
        return cls(
            lora=lora,
            quant=quant,
            engines=engines,
            max_steps=training.get("training_args", {}).get("max_steps", 2000),
            learning_rate=training.get("optimizer", {}).get("learning_rate", 2e-4),
            per_device_batch_size=training.get("batch", {}).get("per_device_train_batch_size", 4),
            gradient_accumulation_steps=training.get("batch", {}).get("gradient_accumulation_steps", 4),
            bf16=training.get("precision", {}).get("bf16", True),
            gradient_checkpointing=training.get("training_args", {}).get("gradient_checkpointing", True),
            unsloth_enabled=training.get("unsloth", {}).get("enabled", True),
        )
