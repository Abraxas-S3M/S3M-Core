"""Langfuse provider configuration for S3M Quad-LLM observability."""

from __future__ import annotations

from dataclasses import dataclass, field


S3M_TRACE_CATEGORIES = {
    "threat_assessment": "Grok reasoning for threat/engagement analysis (Feature 2)",
    "mission_planning": "Mistral planning for OPORD/COA generation (Phase 11)",
    "arabic_nlp": "ALLaM Arabic summarization and entity extraction (Phase 14/19)",
    "tactical_decision": "Phi-3 tactical decisions in behavior trees (Phase 6)",
    "adversary_reasoning": "Grok adversary in wargaming (Phase 18)",
    "maintenance_report": "Mistral maintenance report generation (Phase 17)",
    "intel_briefing": "Mistral+Grok intelligence product generation (Phase 19)",
    "command_processing": "Phi-3 command intent classification (Feature 4)",
    "risk_analysis": "Grok risk assessment reasoning (Feature 3)",
}


@dataclass
class LangfuseConfig:
    base_url: str = "http://localhost:3000"
    trace_categories: dict[str, str] = field(default_factory=lambda: dict(S3M_TRACE_CATEGORIES))
    metrics_retention_days: int = 90
    sampling_rate: float = 1.0
    rate_limit_rpm: int = 60
