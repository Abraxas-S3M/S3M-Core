"""
S3M LLM Monitor Provider v2.0
Real-time visibility into Quad-Engine orchestration.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.dashboard.providers.helpers import clamp_int, normalize_status
from src.llm_core import Orchestrator
from src.llm_core.engine_registry import DOMAIN_ROUTING, TaskDomain

logger = logging.getLogger("s3m.dashboard.llm_monitor")


class LLMMonitorProvider:
    """
    Provides comprehensive LLM system status for dashboard operations.

    Tactical context:
    This provider surfaces confidence and failover posture so operators can
    validate that autonomous recommendations remain in decision-support mode.
    """

    def __init__(self, orchestrator: Optional[Orchestrator] = None) -> None:
        self.orchestrator = orchestrator or Orchestrator()
        self.failover = self.orchestrator.failover
        self.model_registry = self.orchestrator.model_registry
        self.preloader = self.orchestrator.preloader
        self.confidence = self.orchestrator.confidence
        self.last_error: str = ""
        logger.info("LLMMonitorProvider initialized")

    # ========== Legacy-compatible dashboard methods ==========
    def get_engine_status(self) -> List[Dict[str, Any]]:
        """Return 4 engine entries with load status and engine metadata."""
        try:
            health = self.failover.get_health_snapshot()
            configs = self.orchestrator.registry.get_all_engines()
            rows: List[Dict[str, Any]] = []
            for cfg in configs:
                state = health.get(cfg.engine_id.value, {})
                status = str(state.get("state", "unknown")).lower()
                rows.append(
                    {
                        "name": cfg.name,
                        "provider": cfg.provider,
                        "status": "loaded" if status in {"healthy", "degraded"} else "unloaded",
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
            "avg_latency_ms": 0.0,
            "requests_per_minute": 0.0,
            "engines_simulated": 0,
        }
        try:
            from src.api.server import state

            uptime = max(0.0, time.time() - float(getattr(state, "start_time", time.time())))
            total = int(getattr(state, "request_count", 0))
            engine_status = getattr(state, "engine_status", {})
            loaded = sum(1 for value in engine_status.values() if str(value).lower() == "loaded")
            simulated = sum(1 for value in engine_status.values() if str(value).lower() == "simulated")
            history = self.orchestrator.get_routing_history(limit=100)
            latencies = [float(item.get("latency_ms", 0.0)) for item in history]
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
        """Return recent routing decisions as audit entries."""
        bounded = clamp_int(limit, minimum=1, maximum=200, default=20)
        history = self.orchestrator.get_routing_history(limit=bounded)
        out: List[Dict[str, Any]] = []
        for idx, item in enumerate(history):
            out.append(
                {
                    "id": str(item.get("audit_id", f"audit-{idx}")),
                    "timestamp": str(item.get("timestamp", datetime.now(timezone.utc).isoformat())),
                    "action": "llm_route",
                    "details": item,
                }
            )
        return out

    def get_routing(self) -> Dict[str, str]:
        """Return domain routing map for engine orchestration visibility."""
        return {
            TaskDomain.TACTICAL.value: DOMAIN_ROUTING[TaskDomain.TACTICAL].value,
            TaskDomain.REASONING.value: DOMAIN_ROUTING[TaskDomain.REASONING].value,
            TaskDomain.PLANNING.value: DOMAIN_ROUTING[TaskDomain.PLANNING].value,
            TaskDomain.ARABIC_NLP.value: DOMAIN_ROUTING[TaskDomain.ARABIC_NLP].value,
        }

    def health_check(self) -> Dict[str, Any]:
        health = self.orchestrator.check_system_health()
        status = "operational" if health["overall_status"] == "HEALTHY" else "degraded"
        return {
            "status": normalize_status(status),
            "detail": "engine telemetry available",
            "active": status == "operational",
            "last_error": self.last_error,
        }

    # ========== v2 orchestrator dashboards ==========
    def get_orchestrator_status(self) -> Dict:
        health = self.orchestrator.check_system_health()
        return {
            "overall_status": health["overall_status"],
            "timestamp": datetime.utcnow().isoformat(),
            "models": health["models"],
            "engines": health["engines"],
            "failover": health["failover"],
            "issues": health["issues"],
        }

    def get_routing_intelligence(self) -> Dict:
        history = self.orchestrator.get_routing_history(limit=10)
        strategy_counts: Dict[str, int] = {}
        for decision in history:
            strategy = str(decision.get("strategy", "UNKNOWN"))
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        avg_latency = (
            sum(float(item.get("latency_ms", 0.0)) for item in history) / len(history)
            if history
            else 0.0
        )
        return {
            "recent_decisions": history,
            "strategy_distribution": strategy_counts,
            "avg_latency_ms": avg_latency,
        }

    def get_engine_health_dashboard(self) -> Dict:
        health = self.failover.get_health_snapshot()
        engines_info: Dict[str, Dict[str, Any]] = {}
        for engine_id, state_dict in health.items():
            if not isinstance(state_dict, dict):
                continue
            engines_info[engine_id] = {
                "state": state_dict.get("state"),
                "success_rate": f"{float(str(state_dict.get('success_rate', '0%')).rstrip('%')) / 100.0:.1%}"
                if isinstance(state_dict.get("success_rate"), str)
                else state_dict.get("success_rate"),
                "last_success": state_dict.get("last_success_time") or state_dict.get("last_success"),
                "last_failure": state_dict.get("last_failure_time") or state_dict.get("last_failure"),
                "failure_reason": state_dict.get("failure_reason"),
                "uses_in_window": state_dict.get("use_count_in_window", 0),
            }
        return engines_info

    def get_confidence_dashboard(self) -> Dict:
        scoring_history = self.confidence.get_scoring_history(limit=50)
        if scoring_history:
            scores = [float(item["score"]) for item in scoring_history]
            avg_score = sum(scores) / len(scores)
            accept_rate = sum(1 for score in scores if score >= 0.80) / len(scores)
            review_rate = sum(1 for score in scores if 0.60 <= score < 0.80) / len(scores)
            reject_rate = sum(1 for score in scores if score < 0.60) / len(scores)
        else:
            avg_score = 0.0
            accept_rate = review_rate = reject_rate = 0.0
        return {
            "avg_confidence": round(avg_score, 4),
            "accept_rate": round(accept_rate, 2),
            "review_rate": round(review_rate, 2),
            "reject_rate": round(reject_rate, 2),
            "recent_scores": [
                {
                    "score": item["score"],
                    "status": item["status"],
                    "audit_id": item.get("audit_id"),
                    "timestamp": item.get("timestamp"),
                }
                for item in scoring_history[-20:]
            ],
        }

    def get_failover_status(self) -> Dict:
        failover_history = self.failover.get_failover_history(limit=20)
        return {
            "active": True,
            "total_activations": len(failover_history),
            "recent_activations": [
                {
                    "primary": event.get("primary_engine") or event.get("primary"),
                    "fallback_tried": event.get("fallback_engines_tried") or event.get("fallbacks_tried"),
                    "fallback_succeeded": event.get("fallback_engines_succeeded") or event.get("succeeded"),
                    "reason": event.get("reason"),
                    "recovery_time_ms": event.get("recovery_time_ms") or event.get("latency_ms"),
                }
                for event in failover_history
            ],
        }

    def get_model_verification_status(self) -> Dict:
        registry_status = self.model_registry.list_registry_status(recompute=False)
        artifacts_detail: Dict[str, Dict[str, Any]] = {}
        for engine_id, artifact in registry_status.artifacts.items():
            artifacts_detail[engine_id] = {
                "status": artifact.status,
                "version": artifact.version_tag,
                "last_verified": artifact.last_verified_at[:10] if artifact.last_verified_at else "",
                "age_days": artifact.age_since_verification_days(),
                "drift_reason": artifact.drift_reason,
            }
        return {
            "overall": registry_status.summary(),
            "clean_artifacts": registry_status.clean_artifacts,
            "missing_artifacts": registry_status.missing_artifacts,
            "mismatched_artifacts": registry_status.mismatched_artifacts,
            "stale_artifacts": registry_status.stale_artifacts,
            "review_required": registry_status.review_required,
            "artifacts": artifacts_detail,
        }

    def get_preload_intelligence(self) -> Dict:
        stats = self.preloader.get_stats()
        prediction = (
            self.preloader.predict_next_engines(limit=3) if stats.get("total_requests", 0) > 0 else None
        )
        return {
            "total_requests_tracked": stats["total_requests"],
            "engines_used": stats["engines_used"],
            "domains_used": stats["domains_used"],
            "most_common_domain": stats["most_common_domain"],
            "most_used_engine": stats["most_used_engine"],
            "current_prediction": {
                "engines": [engine.value for engine in prediction.predicted_engines],
                "confidence": prediction.confidence,
            }
            if prediction
            else None,
            "recent_history": [
                {
                    "domain": item["domain"],
                    "engine": item["engine"],
                    "success": item["success"],
                }
                for item in self.preloader.get_history(limit=10)
            ],
        }

    def get_full_system_dashboard(self) -> Dict:
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "orchestrator": self.get_orchestrator_status(),
            "routing": self.get_routing_intelligence(),
            "engines": self.get_engine_health_dashboard(),
            "confidence": self.get_confidence_dashboard(),
            "failover": self.get_failover_status(),
            "models": self.get_model_verification_status(),
            "preload": self.get_preload_intelligence(),
        }

    def get_alerts(self) -> List[Dict]:
        alerts: List[Dict] = []
        model_status = self.model_registry.list_registry_status()
        if model_status.missing_artifacts > 0:
            alerts.append(
                {
                    "severity": "CRITICAL",
                    "type": "MODEL_MISSING",
                    "message": f"{model_status.missing_artifacts} models missing",
                    "action": "Redeploy models",
                }
            )
        if model_status.mismatched_artifacts > 0:
            alerts.append(
                {
                    "severity": "CRITICAL",
                    "type": "MODEL_MISMATCH",
                    "message": f"{model_status.mismatched_artifacts} models corrupted",
                    "action": "Verify hash, redeploy if needed",
                }
            )
        if model_status.stale_artifacts > 0:
            alerts.append(
                {
                    "severity": "WARNING",
                    "type": "STALE_VERIFICATION",
                    "message": f"{model_status.stale_artifacts} models not recently verified",
                    "action": "Run verification sweep",
                }
            )

        health = self.failover.get_health_snapshot()
        unavailable_engines = [
            engine_id
            for engine_id, state in health.items()
            if isinstance(state, dict) and str(state.get("state", "")).lower() == "unavailable"
        ]
        if unavailable_engines:
            alerts.append(
                {
                    "severity": "WARNING",
                    "type": "ENGINE_UNAVAILABLE",
                    "message": f"Engines unavailable: {unavailable_engines}",
                    "action": "Check failover logs, consider restart",
                }
            )
        return alerts

    @staticmethod
    def _unknown_stub(index: int) -> Dict[str, Any]:
        names = ["Phi-3 Medium", "Grok", "Mixtral 8x7B", "ALLaM-7B"]
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
