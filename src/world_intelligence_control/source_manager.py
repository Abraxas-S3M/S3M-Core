"""Source resolution for local-versus-fallback World Intelligence serving.

Military/tactical context:
This manager enforces controlled source selection so operator dashboards keep
receiving intelligence without bypassing sovereign gateway policy.
"""

from __future__ import annotations

from .models import SourceDecision, WorldIntelligenceMode, WorldIntelligenceSource
from .runtime_manager import RuntimeManager


class SourceManager:
    """Resolve the active source from mode and runtime health."""

    def __init__(self, runtime_manager: RuntimeManager, fallback_probe) -> None:
        self.runtime_manager = runtime_manager
        self._fallback_probe = fallback_probe

    def resolve_source(self, client_key: str = "global") -> SourceDecision:
        mode = self.runtime_manager.get_mode()
        if mode == WorldIntelligenceMode.EXTERNAL_LIVE:
            return SourceDecision(
                mode=mode,
                source=WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK,
                reason="external live demo mode enabled",
                local_runtime_healthy=False,
                local_runtime_health_url=None,
                local_runtime_status_code=None,
                fallback_available=True,
                training_safe=False,
            )

        local_health = self.runtime_manager.local_runtime_health()
        training_safe = mode == WorldIntelligenceMode.TRAINING_SAFE
        fallback_available = False
        if training_safe or not local_health.healthy:
            fallback_info = self._fallback_probe(client_key=client_key)
            fallback_available = bool(fallback_info.get("available", False))
        base_decision = {
            "local_runtime_healthy": local_health.healthy,
            "local_runtime_health_url": local_health.endpoint,
            "local_runtime_status_code": local_health.status_code,
            "fallback_available": fallback_available,
            "training_safe": training_safe,
        }

        if mode == WorldIntelligenceMode.OFFLINE_SAFE:
            return SourceDecision(
                mode=mode,
                source=WorldIntelligenceSource.OFFLINE_SAFE,
                reason="offline_safe mode set by policy",
                **base_decision,
            )

        if mode == WorldIntelligenceMode.TRAINING_SAFE:
            if fallback_available:
                return SourceDecision(
                    mode=mode,
                    source=WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK,
                    reason="training_safe enforces external read-only fallback",
                    **base_decision,
                )
            return SourceDecision(
                mode=mode,
                source=WorldIntelligenceSource.OFFLINE_SAFE,
                reason="training_safe with unavailable fallback",
                **base_decision,
            )

        if local_health.healthy:
            return SourceDecision(
                mode=mode,
                source=WorldIntelligenceSource.LOCAL_SELF_HOSTED,
                reason="local runtime healthy",
                **base_decision,
            )

        if fallback_available and self.runtime_manager.fallback_enabled:
            return SourceDecision(
                mode=mode,
                source=WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK,
                reason="local runtime unavailable, switched to external fallback",
                **base_decision,
            )

        return SourceDecision(
            mode=WorldIntelligenceMode.OFFLINE_SAFE,
            source=WorldIntelligenceSource.OFFLINE_SAFE,
            reason="both local and fallback sources unavailable",
            **base_decision,
        )
