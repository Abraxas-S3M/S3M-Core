"""Configuration for SDAIA ALLaM sovereign provider wrapper."""

from dataclasses import dataclass, field


ALLAM_MODELS = {
    "allam-7b": {
        "model_id": "sdaia/allam-7b",
        "parameters": "7B",
        "languages": ["ar", "en"],
        "use_cases": ["summarization", "translation", "ner", "classification", "generation"],
        "quantizations": ["fp16", "int8", "int4"],
        "recommended_quantization": "int8",
        "vram_fp16_gb": 14,
        "vram_int8_gb": 7,
        "vram_int4_gb": 4,
    },
    "allam-7b-chat": {
        "model_id": "sdaia/allam-7b-chat",
        "parameters": "7B",
        "languages": ["ar", "en"],
        "use_cases": ["conversation", "instruction_following", "military_command_parsing"],
        "quantizations": ["fp16", "int8", "int4"],
        "recommended_quantization": "int8",
        "vram_fp16_gb": 14,
        "vram_int8_gb": 7,
        "vram_int4_gb": 4,
    },
}

S3M_ALLAM_USAGE = {
    "comms_summarization": "Phase 14 — Arabic message summarization in secure comms",
    "intel_briefing_ar": "Phase 19 — Arabic intelligence briefing generation",
    "entity_extraction_ar": "Phase 14/19 — Arabic named entity recognition for military text",
    "command_parsing_ar": "Feature 4 — Arabic voice/text command interpretation",
    "translation_ar_en": "Cross-layer — Arabic↔English military translation",
    "threat_classification_ar": "Phase 5 — Arabic threat indicator classification",
}


@dataclass
class SDAIAAllamConfig:
    api_url: str = "https://api.sdaia.gov.sa/allam/v1"
    rate_limit_rpm: int = 30
    local_model_dir: str = "models/arabic/allam/"
    allam_models: dict = field(default_factory=lambda: dict(ALLAM_MODELS))
    arabic_benchmarks: list[str] = field(
        default_factory=lambda: ["ARCD", "ORCA", "AraBench", "ArabicGLUE", "S3M_MilitaryArabic"]
    )
    s3m_usage_contexts: dict = field(default_factory=lambda: dict(S3M_ALLAM_USAGE))
