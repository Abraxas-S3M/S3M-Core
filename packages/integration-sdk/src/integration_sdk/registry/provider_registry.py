"""Central provider registry with mode control, health checks, and feature flags."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Type

from integration_sdk.base.provider_adapter import (
    OperatingMode,
    ProviderAdapter,
    ProviderCategory,
    ProviderHealth,
    ProviderManifest,
)
from integration_sdk.errors.integration_errors import IntegrationConfigurationError

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


class ProviderRegistry:
    """Registry and runtime controller for all provider adapters."""

    def __init__(self, config_path: Optional[str] = None) -> None:
        root = Path(__file__).resolve()
        while root != root.parent and not (root / "configs").exists():
            root = root.parent
        self.config_path = Path(config_path) if config_path else root / "configs" / "integrations" / "providers.yaml"

        self._adapter_classes: Dict[str, Type[ProviderAdapter]] = {}
        self._instances: Dict[str, ProviderAdapter] = {}
        self._enabled: Dict[str, bool] = {}
        self._provider_modes: Dict[str, OperatingMode] = {}

        config = self._load_config()
        self._global_mode = OperatingMode(config.get("global", {}).get("default_mode", "online"))
        self._provider_config = config.get("providers", {}) or {}

    def _load_config(self) -> Dict[str, object]:
        if not self.config_path.exists():
            return {"global": {"default_mode": "online"}, "providers": {}}
        if yaml is None:
            raise IntegrationConfigurationError("PyYAML is required to load provider config")
        with self.config_path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {"global": {"default_mode": "online"}, "providers": {}}

    def register(self, adapter_class: Type[ProviderAdapter]) -> None:
        adapter = adapter_class(mode=self._global_mode)
        manifest = adapter.get_manifest()
        if manifest.provider_id in self._adapter_classes:
            raise IntegrationConfigurationError(f"Provider already registered: {manifest.provider_id}")

        provider_cfg = self._provider_config.get(manifest.provider_id, {})
        enabled = bool(provider_cfg.get("enabled", manifest.enabled))
        mode_str = provider_cfg.get("mode", self._global_mode.value)
        mode = OperatingMode(mode_str)

        self._adapter_classes[manifest.provider_id] = adapter_class
        self._enabled[manifest.provider_id] = enabled
        self._provider_modes[manifest.provider_id] = mode

    def _build_instance(self, provider_id: str) -> ProviderAdapter:
        adapter_class = self._adapter_classes[provider_id]
        mode = self._provider_modes.get(provider_id, self._global_mode)
        instance = adapter_class(mode=mode)
        self._instances[provider_id] = instance
        return instance

    def get(self, provider_id: str) -> Optional[ProviderAdapter]:
        if provider_id not in self._adapter_classes:
            return None
        if not self._enabled.get(provider_id, True):
            return None
        return self._instances.get(provider_id) or self._build_instance(provider_id)

    def get_all(self, category: ProviderCategory = None, enabled_only: bool = True) -> List[ProviderAdapter]:
        adapters: List[ProviderAdapter] = []
        for provider_id, adapter_class in self._adapter_classes.items():
            if enabled_only and not self._enabled.get(provider_id, True):
                continue
            adapter = self._instances.get(provider_id)
            if adapter is None:
                adapter = adapter_class(mode=self._provider_modes.get(provider_id, self._global_mode))
                self._instances[provider_id] = adapter
            if category and adapter.get_manifest().category != category:
                continue
            adapters.append(adapter)
        return adapters

    def enable(self, provider_id: str) -> None:
        if provider_id in self._adapter_classes:
            self._enabled[provider_id] = True

    def disable(self, provider_id: str) -> None:
        if provider_id in self._adapter_classes:
            self._enabled[provider_id] = False

    def set_mode(self, provider_id: str, mode: OperatingMode) -> None:
        if provider_id not in self._adapter_classes:
            return
        self._provider_modes[provider_id] = mode
        if provider_id in self._instances:
            self._instances[provider_id].set_mode(mode)

    def set_global_mode(self, mode: OperatingMode) -> None:
        self._global_mode = mode
        for provider_id in self._adapter_classes:
            self._provider_modes[provider_id] = mode
        for adapter in self._instances.values():
            adapter.set_mode(mode)

    def health_check_all(self) -> Dict[str, Dict]:
        status: Dict[str, Dict] = {}
        for provider_id, adapter_class in self._adapter_classes.items():
            if not self._enabled.get(provider_id, True):
                status[provider_id] = {
                    "status": ProviderHealth.DISABLED,
                    "latency_ms": None,
                    "last_successful_fetch": None,
                    "error_count": 0,
                    "detail": "Provider disabled by feature flag",
                }
                continue
            adapter = self._instances.get(provider_id)
            if adapter is None:
                adapter = adapter_class(mode=self._provider_modes.get(provider_id, self._global_mode))
                self._instances[provider_id] = adapter
            status[provider_id] = adapter.health_check()
        return status

    def get_manifest(self, provider_id: str) -> ProviderManifest:
        if provider_id not in self._adapter_classes:
            raise IntegrationConfigurationError(f"Unknown provider: {provider_id}")
        adapter = self._instances.get(provider_id)
        if adapter is None:
            adapter = self._build_instance(provider_id)
        return adapter.get_manifest()

    def get_stats(self) -> dict:
        by_category = Counter()
        by_tier = Counter()
        by_health = Counter()

        for provider_id, adapter_class in self._adapter_classes.items():
            adapter = self._instances.get(provider_id)
            if adapter is None:
                adapter = adapter_class(mode=self._provider_modes.get(provider_id, self._global_mode))
                self._instances[provider_id] = adapter

            manifest = adapter.get_manifest()
            by_category[manifest.category.value] += 1
            by_tier[manifest.tier.value] += 1
            health = adapter.health_check().get("status", ProviderHealth.OFFLINE)
            health_value = health.value if isinstance(health, ProviderHealth) else str(health)
            by_health[health_value] += 1

        return {
            "total_providers": len(self._adapter_classes),
            "enabled_providers": sum(1 for p in self._adapter_classes if self._enabled.get(p, True)),
            "by_category": dict(by_category),
            "by_tier": dict(by_tier),
            "by_health": dict(by_health),
            "global_mode": self._global_mode.value,
        }
