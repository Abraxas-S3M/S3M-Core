"""ClearML provider configuration for S3M retraining orchestration."""

from dataclasses import dataclass, field
import os


S3M_CLEARML_PIPELINES = {
    "sar_retrain": "SAR detection model retraining when new labeled data arrives from Label Studio",
    "rul_retrain": "RUL model retraining on new telemetry data from Phase 17",
    "arabic_finetune": "Arabic NLP fine-tuning on new military text corpus",
    "yolo_finetune": "YOLO object detection fine-tuning on new annotated imagery",
}


@dataclass
class ClearMLConfig:
    base_url: str = field(default_factory=lambda: os.getenv("S3M_CLEARML_API_HOST", os.getenv("CLEARML_API_HOST", "http://localhost:8008")))
    rate_limit_rpm: int = 30
    s3m_pipelines: dict[str, str] = field(default_factory=lambda: dict(S3M_CLEARML_PIPELINES))
    offline_mode: bool = field(default_factory=lambda: os.getenv("CLEARML_OFFLINE_MODE", "").strip().lower() in {"1", "true", "yes"})
