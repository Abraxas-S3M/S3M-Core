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
        local_health = self.runtime_manager.local_runtime_health()
        fallback_info = self._fallback_probe(client_key=client_key)
        fallback_available = bool(fallback_info.get("available", False))
        training_safe = mode == WorldIntelligenceMode.TRAINING_SAFE

        if mode == WorldIntelligenceMode.OFFLINE_SAFE:
            return SourceDecision(
                mode=mode,
                source=WorldIntelligenceSource.OFFLINE_SAFE,
                reason="offline_safe mode set by policy",
                local_runtime_healthy=local_health.healthy,
                fallback_available=fallback_available,
                training_safe=training_safe,
            )

        if mode == WorldIntelligenceMode.TRAINING_SAFE:
            if fallback_available:
                return SourceDecision(
                    mode=mode,
                    source=WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK,
                    reason="training_safe enforces external read-only fallback",
                    local_runtime_healthy=local_health.healthy,
                    fallback_available=fallback_available,
                    training_safe=training_safe,
                )
            return SourceDecision(
                mode=mode,
                source=WorldIntelligenceSource.OFFLINE_SAFE,
                reason="training_safe with unavailable fallback",
                local_runtime_healthy=local_health.healthy,
                fallback_available=fallback_available,
                training_safe=training_safe,
            )

        if local_health.healthy:
            return SourceDecision(
                mode=mode,
                source=WorldIntelligenceSource.LOCAL_SELF_HOSTED,
                reason="local runtime healthy",
                local_runtime_healthy=local_health.healthy,
                fallback_available=fallback_available,
                training_safe=training_safe,
            )

        if fallback_available and self.runtime_manager.fallback_enabled:
            return SourceDecision(
                mode=mode,
                source=WorldIntelligenceSource.EXTERNAL_LIVE_FALLBACK,
                reason="local runtime unavailable, switched to external fallback",
                local_runtime_healthy=local_health.healthy,
                fallback_available=fallback_available,
                training_safe=training_safe,
            )

        return SourceDecision(
            mode=WorldIntelligenceMode.OFFLINE_SAFE,
            source=WorldIntelligenceSource.OFFLINE_SAFE,
            reason="both local and fallback sources unavailable",
            local_runtime_healthy=local_health.healthy,
            fallback_available=fallback_available,
            training_safe=training_safe,
        )
