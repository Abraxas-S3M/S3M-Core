"""Hugging Face provider configuration for S3M model governance."""

from __future__ import annotations

from dataclasses import dataclass, field


S3M_MODEL_REGISTRY: dict[str, dict[str, object]] = {
    "phi-3-mini-4k": {
        "repo": "microsoft/Phi-3-mini-4k-instruct",
        "pipeline": "text-generation",
        "layer": "llm_core",
        "quantized": True,
    },
    "phi-3-medium": {
        "repo": "microsoft/Phi-3-medium-4k-instruct",
        "pipeline": "text-generation",
        "layer": "llm_core",
        "quantized": True,
    },
    "mistral-7b": {
        "repo": "mistralai/Mistral-7B-Instruct-v0.2",
        "pipeline": "text-generation",
        "layer": "llm_core",
        "quantized": True,
    },
    "arabert": {
        "repo": "aubmindlab/bert-base-arabertv2",
        "pipeline": "fill-mask",
        "layer": "comms_nlp",
        "quantized": False,
    },
    "mt5-arabic": {
        "repo": "csebuetnlp/mT5_multilingual_XLSum",
        "pipeline": "summarization",
        "layer": "comms_nlp",
        "quantized": False,
    },
    "camelbert": {
        "repo": "CAMeL-Lab/bert-base-arabic-camelbert-mix",
        "pipeline": "fill-mask",
        "layer": "comms_nlp",
        "quantized": False,
    },
    "yolov8n": {
        "repo": "ultralytics/yolov8n",
        "pipeline": "object-detection",
        "layer": "threat_detection",
        "quantized": True,
    },
    "whisper-base": {
        "repo": "openai/whisper-base",
        "pipeline": "automatic-speech-recognition",
        "layer": "command_agent",
        "quantized": True,
    },
    "sar-ship-detect": {
        "repo": "custom/sar-ship-yolov8",
        "pipeline": "object-detection",
        "layer": "sensor_analytics",
        "quantized": True,
    },
}


@dataclass
class HuggingFaceConfig:
    hub_api_url: str = "https://huggingface.co/api"
    inference_api_url: str = "https://api-inference.huggingface.co/models"
    rate_limit_rpm: int = 30
    local_cache_dir: str = "models/"
    s3m_model_registry: dict[str, dict[str, object]] = field(default_factory=lambda: dict(S3M_MODEL_REGISTRY))
    offline_model_manifest_path: str = "configs/integrations/model_manifest.yaml"
