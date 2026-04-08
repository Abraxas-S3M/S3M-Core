"""Langfuse adapter for S3M Quad-LLM observability and scoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from packages.providers.base import ProviderAdapter, ProviderCategory, ProviderManifest, ProviderTier

from .config import LangfuseConfig


class LangfuseAdapter(ProviderAdapter):
    def __init__(self, config: LangfuseConfig | None = None, mode: str = "airgapped") -> None:
        super().__init__(mode=mode)
        self.config = config or LangfuseConfig()

    def _fixture_dir(self) -> Path:
        return Path(__file__).resolve().parent

    def _env(self, key: str, default: str = "") -> str:
        import os

        return os.getenv(f"S3M_{key}", os.getenv(key, default))

    def get_manifest(self) -> ProviderManifest:
        return ProviderManifest(
            provider_id="ml-langfuse",
            category=ProviderCategory.AI_ML_SERVICES,
            tier=ProviderTier.FREE,
            auth_type="api_key",
            rate_limit_rpm=60,
            required_env_vars=["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"],
            optional_env_vars=["LANGFUSE_HOST"],
            supported_schemas=["LLMTrace", "LLMMetrics", "LLMHealth"],
        )

    def validate_credentials(self) -> dict[str, Any]:
        if self.mode == "airgapped":
            return {"valid": True, "mode": "airgapped"}
        return {
            "valid": bool(self._env("LANGFUSE_PUBLIC_KEY") and self._env("LANGFUSE_SECRET_KEY")),
            "host": self._env("LANGFUSE_HOST", self.config.base_url),
        }

    def _traces(self) -> list[dict[str, Any]]:
        return list(self._load_fixture_json("traces_list.json").get("traces", []))

    def get_traces(self, category: str | None = None, limit: int = 50) -> dict[str, Any]:
        traces = self._traces()
        if category:
            traces = [trace for trace in traces if trace.get("category") == category]
        return {"traces": traces[:limit], "count": min(len(traces), limit)}

    def get_daily_metrics(self, days: int = 7) -> dict[str, Any]:
        fixture = self._load_fixture_json("daily_metrics.json")
        metrics = list(fixture.get("days", fixture.get("daily", [])))
        return {"days": metrics[:days], "count": min(len(metrics), days)}

    def get_model_performance(self) -> dict[str, Any]:
        return self._load_fixture_json("model_performance.json")

    def get_category_breakdown(self) -> dict[str, Any]:
        traces = self._traces()
        bucket: dict[str, dict[str, Any]] = {}
        for trace in traces:
            category = str(trace.get("category", "unknown"))
            row = bucket.setdefault(category, {"calls": 0, "avg_latency_ms": 0.0, "errors": 0})
            row["calls"] += 1
            row["avg_latency_ms"] += float(trace.get("latency_ms", 0.0))
            row["errors"] += 1 if str(trace.get("status", "ok")).lower() in {"error", "failed"} else 0
        for row in bucket.values():
            calls = max(int(row["calls"]), 1)
            row["avg_latency_ms"] = round(float(row["avg_latency_ms"]) / calls, 2)
        categories: list[dict[str, Any]] = []
        for category, row in bucket.items():
            categories.append(
                {
                    "category": category,
                    "calls": row["calls"],
                    "avg_latency_ms": row["avg_latency_ms"],
                    "errors": row["errors"],
                }
            )
        categories.sort(key=lambda item: int(item["calls"]), reverse=True)
        return {"categories": categories}

    def log_score(self, trace_id: str, name: str, value: float, comment: str | None = None) -> dict[str, Any]:
        # Tactical context: post-mission scoring captures operator trust in LLM outputs for retraining.
        return {
            "trace_id": trace_id,
            "name": name,
            "value": float(value),
            "comment": comment,
            "logged_at": datetime.now(tz=UTC).isoformat(),
            "status": "logged",
        }

    def get_cost_summary(self, days: int = 30) -> dict[str, Any]:
        traces = [trace for trace in self._traces() if datetime.now(tz=UTC) - self._parse_ts(str(trace.get("timestamp"))) <= timedelta(days=days)]
        prices = {"phi-3": 0.05, "grok-1": 0.4, "mixtral-8x7b": 0.08, "allam": 0.07}
        by_model: dict[str, dict[str, Any]] = {}
        for trace in traces:
            model = str(trace.get("model", "unknown")).lower()
            tokens = int(trace.get("tokens", 0))
            row = by_model.setdefault(model, {"tokens": 0, "estimated_cost_usd": 0.0})
            row["tokens"] += tokens
            row["estimated_cost_usd"] += (tokens / 1000.0) * prices.get(model, 0.1)
        for row in by_model.values():
            row["estimated_cost_usd"] = round(float(row["estimated_cost_usd"]), 4)
        total_cost = round(sum(float(item["estimated_cost_usd"]) for item in by_model.values()), 4)
        return {"days": days, "by_model": by_model, "total_estimated_cost_usd": total_cost}

    def _parse_ts(self, value: str) -> datetime:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return datetime.now(tz=UTC)

    def get_llm_health(self) -> dict[str, Any]:
        traces = self._traces()
        engines = {"phi-3": [], "grok-1": [], "mixtral-8x7b": [], "allam": []}
        for trace in traces:
            model = str(trace.get("model", "")).lower()
            if model in engines:
                engines[model].append(trace)
        payload: dict[str, dict[str, Any]] = {}
        display = {"phi-3": "Phi-3", "grok-1": "Grok", "mixtral-8x7b": "Mistral", "allam": "ALLaM"}
        failing = 0
        for model_name, rows in engines.items():
            pretty_name = display[model_name]
            if not rows:
                payload[pretty_name] = {"status": "failing", "avg_latency_ms": None, "last_call": None}
                failing += 1
                continue
            avg_latency = round(mean(float(row.get("latency_ms", 0.0)) for row in rows), 2)
            last_call = max(rows, key=lambda row: self._parse_ts(str(row.get("timestamp")))).get("timestamp")
            errors = sum(1 for row in rows if str(row.get("status", "ok")).lower() in {"error", "failed"})
            status = "healthy" if errors == 0 else ("degraded" if errors < len(rows) else "failing")
            if status != "healthy":
                failing += 1
            payload[pretty_name] = {"status": status, "avg_latency_ms": avg_latency, "last_call": last_call}
        overall = "healthy" if failing == 0 else ("degraded" if failing < len(engines) else "failing")
        return {"engines": payload, "overall": overall}

    def fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        action = str(params.get("action", "health")).lower()
        if action == "traces":
            return self.get_traces(params.get("category"), int(params.get("limit", 50)))
        if action == "daily_metrics":
            return self.get_daily_metrics(int(params.get("days", 7)))
        if action == "model_performance":
            return self.get_model_performance()
        if action == "category_breakdown":
            return self.get_category_breakdown()
        if action == "cost":
            return self.get_cost_summary(int(params.get("days", 30)))
        if action == "metrics":
            return self.get_daily_metrics(int(params.get("days", 7)))
        return self.get_llm_health()

    def normalize(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        return raw_data

    def health_check(self) -> dict[str, Any]:
        health = self.get_llm_health()
        return {"status": "ok" if health.get("overall") in {"healthy", "degraded"} else "degraded", "detail": health}
