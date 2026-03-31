"""Dashboard provider for Layer 01 LLM monitoring and audit visibility."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from src.dashboard.providers.helpers import clamp_int, normalize_status


class LLMMonitorProvider:
    """Expose quad-engine runtime status for tactical command dashboards."""

    def __init__(self) -> None:
        self.last_error: str = ""

    def get_engine_status(self) -> List[Dict[str, Any]]:
        """Return 4 engine entries with load status and engine metadata."""
        try:
            from src.llm_core.engine_registry import EngineRegistry

            registry = EngineRegistry()
            configs = registry.get_all_engines()
            active_map = registry.get_status() if hasattr(registry, "get_status") else {}
            rows: List[Dict[str, Any]] = []
            for cfg in configs:
                active = bool(active_map.get(cfg.engine_id.value, cfg.loaded))
                rows.append(
                    {
                        "name": cfg.name,
                        "provider": cfg.provider,
                        "status": "loaded" if active else "unloaded",
                        "domain": cfg.primary_domain.value,
                        "params": cfg.params,
                        "quantization": cfg.quantization,
                    }
                )
            while len(rows) < 4:
                rows.append(self._unknown_stub(len(rows)))
            return rows[:4]
        except Exception as exc:
            self.last_error = str(exc)
            return [self._unknown_stub(i) for i in range(4)]

    def get_metrics(self) -> Dict[str, Any]:
        """Return request counters and inferred throughput metrics."""
        base = {
            "total_requests": 0,
            "uptime_seconds": 0,
            "engines_loaded": 0,
            "avg_latency_ms": 0,
            "requests_per_minute": 0,
            "engines_simulated": 0,
        }
        try:
            from src.api.server import state

            uptime = max(0.0, time.time() - float(getattr(state, "start_time", time.time())))
            total = int(getattr(state, "request_count", 0))
            engine_status = getattr(state, "engine_status", {})
            loaded = sum(1 for val in engine_status.values() if str(val).lower() == "loaded")
            simulated = sum(1 for val in engine_status.values() if str(val).lower() == "simulated")
            audit = list(getattr(state, "audit_log", []))
            latencies: List[float] = []
            for entry in audit:
                if not isinstance(entry, dict):
                    continue
                details = entry.get("details")
                if not isinstance(details, dict):
                    continue
                try:
                    latencies.append(float(details.get("latency_ms", 0)))
                except Exception:
                    continue
            avg_latency = (sum(latencies) / len(latencies)) if latencies else 0.0
            rpm = (total / uptime) * 60.0 if uptime > 0 else 0.0
            return {
                "total_requests": total,
                "uptime_seconds": int(uptime),
                "engines_loaded": loaded,
                "avg_latency_ms": round(avg_latency, 2),
                "requests_per_minute": round(rpm, 2),
                "engines_simulated": simulated,
            }
        except Exception as exc:
            self.last_error = str(exc)
            return base

    def get_audit_log(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return most recent server audit entries."""
        safe_limit = clamp_int(limit, minimum=1, maximum=200, default=20)
        try:
            from src.api.server import state

            raw = list(getattr(state, "audit_log", []))
            selected = raw[-safe_limit:]
            out: List[Dict[str, Any]] = []
            for idx, entry in enumerate(selected):
                if not isinstance(entry, dict):
                    continue
                out.append(
                    {
                        "id": str(entry.get("id", f"audit-{idx}")),
                        "timestamp": str(
                            entry.get("timestamp", datetime.now(timezone.utc).isoformat())
                        ),
                        "action": str(entry.get("action", "unknown")),
                        "details": entry.get("details", {}),
                    }
                )
            return out
        except Exception as exc:
            self.last_error = str(exc)
            return []

    def get_routing(self) -> Dict[str, str]:
        """Return domain routing map for engine orchestration visibility."""
        try:
            from src.api.server import state

            routing = getattr(state, "domain_routing", {})
            if isinstance(routing, dict):
                return {str(k): str(v) for k, v in routing.items()}
        except Exception as exc:
            self.last_error = str(exc)
        return {
            "tactical": "phi3",
            "intelligence": "grok",
            "logistics": "mistral",
            "arabic": "allam",
            "general": "phi3",
        }

    def health_check(self) -> Dict[str, Any]:
        engines = self.get_engine_status()
        unknown_count = sum(1 for item in engines if item.get("status") == "unknown")
        if unknown_count == len(engines):
            status = "degraded"
            detail = "engine registry unavailable; using fallback stubs"
        else:
            status = "operational"
            detail = "engine telemetry available"
        return {
            "status": normalize_status(status),
            "detail": detail,
            "active": status == "operational",
            "last_error": self.last_error,
        }

    @staticmethod
    def _unknown_stub(index: int) -> Dict[str, Any]:
        names = ["Phi-3 Mini", "Grok", "Mistral 7B", "ALLaM-7B"]
        providers = ["Microsoft", "xAI", "Mistral AI", "SDAIA"]
        domains = ["tactical", "reasoning", "planning", "arabic_nlp"]
        params = ["3.8B", "8B", "7B", "7B"]
        idx = index % 4
        return {
            "name": names[idx],
            "provider": providers[idx],
            "status": "unknown",
            "domain": domains[idx],
            "params": params[idx],
            "quantization": "unknown",
        }
