"""Provider registry for GEOINT adapters."""

from __future__ import annotations

from typing import Any


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Any] = {}

    def register(self, provider_cls: Any) -> None:
        manifest = provider_cls(mode="airgapped").get_manifest()
        self._providers[manifest.provider_id] = provider_cls

    def get(self, provider_id: str, mode: str = "airgapped") -> Any:
        return self._providers[provider_id](mode=mode)

    def list_provider_ids(self) -> list[str]:
        return sorted(self._providers.keys())

    def register_defaults(self) -> None:
        from packages.providers.geoint_copernicus.adapter import CopernicusAdapter
        from packages.providers.geoint_gee.adapter import GEEAdapter
        from packages.providers.geoint_nasa_earthdata.adapter import NASAEarthdataAdapter
        from packages.providers.geoint_sentinelhub.adapter import SentinelHubAdapter
        from packages.providers.osint_acled.adapter import ACLEDAdapter
        from packages.providers.osint_gdelt.adapter import GDELTAdapter
        from packages.providers.osint_intelligencex.adapter import IntelligenceXAdapter
        from packages.providers.osint_mediacloud.adapter import MediaCloudAdapter

        for cls in [
            CopernicusAdapter,
            SentinelHubAdapter,
            NASAEarthdataAdapter,
            GEEAdapter,
            GDELTAdapter,
            ACLEDAdapter,
            MediaCloudAdapter,
            IntelligenceXAdapter,
        ]:
            self.register(cls)
