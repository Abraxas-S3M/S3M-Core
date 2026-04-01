"""Normalization helpers for SDAIA ALLaM governance metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class SDAIAAllamNormalizer:
    """Normalize ALLaM operational data for sovereign reporting pipelines."""

    def normalize_benchmark_result(self, benchmark: dict[str, Any]) -> dict[str, Any]:
        return {
            "benchmark_name": benchmark.get("name", "unknown"),
            "score": float(benchmark.get("score", 0.0)),
            "metric": benchmark.get("metric", "score"),
            "model_version": benchmark.get("model_version", "allam-7b"),
            "timestamp": benchmark.get("date", datetime.now(timezone.utc).isoformat()),
            "hardware": "Jetson AGX Orin 64GB",
        }

    def normalize_usage_report(self, usage: dict[str, Any]) -> dict[str, Any]:
        return {
            "period": usage.get("period", "30d"),
            "total_calls": int(usage.get("total_calls", 0)),
            "by_context": usage.get("by_context", {}),
            "avg_latency_ms": float(usage.get("avg_latency_ms", 0.0)),
            "total_tokens": int(usage.get("total_tokens", 0)),
        }

    def normalize_model_info(self, model: dict[str, Any]) -> dict[str, Any]:
        quant = model.get("quantization") or model.get("recommended_quantization") or "int8"
        return {
            "model_id": model.get("model_id", "unknown"),
            "provider": "SDAIA",
            "parameters": model.get("parameters", "unknown"),
            "languages": model.get("languages", ["ar"]),
            "quantization": quant,
            "vram_gb": float(model.get(f"vram_{quant}_gb", model.get("vram_int8_gb", 0.0))),
            "locally_cached": bool(model.get("locally_cached", False)),
        }
