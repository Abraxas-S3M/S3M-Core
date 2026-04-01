"""Weights & Biases provider configuration for S3M training telemetry."""

from dataclasses import dataclass, field
import os


S3M_WANDB_PROJECTS = {
    "s3m-sar-detection": "SAR ship detection model training (Phase 15)",
    "s3m-threat-detection": "YOLO military vehicle detection (Phase 5)",
    "s3m-rul-prediction": "RUL predictive maintenance models (Phase 17)",
    "s3m-rl-autonomy": "RL agent training for drone autonomy (Phase 6)",
    "s3m-arabic-nlp": "Arabic NLP fine-tuning (Phase 14)",
    "s3m-wargaming-adversary": "LLM adversary calibration (Phase 18)",
}


@dataclass
class WandBConfig:
    base_url: str = field(default_factory=lambda: os.getenv("S3M_WANDB_BASE_URL", os.getenv("WANDB_BASE_URL", "https://api.wandb.ai")))
    rate_limit_rpm: int = 60
    s3m_projects: dict[str, str] = field(default_factory=lambda: dict(S3M_WANDB_PROJECTS))
    entity: str = field(default_factory=lambda: os.getenv("S3M_WANDB_ENTITY", "s3m"))
    offline_mode: bool = field(default_factory=lambda: os.getenv("WANDB_MODE", "").strip().lower() == "offline")
