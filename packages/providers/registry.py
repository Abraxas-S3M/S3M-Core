"""Provider registry for CTI adapter discovery."""

from __future__ import annotations

import importlib
from typing import Any


_PROVIDER_CLASS_PATHS: dict[str, str] = {
    "cyber-misp": "packages.providers.cyber-misp.adapter:MISPThreatIntelAdapter",
    "cyber-opencti": "packages.providers.cyber-opencti.adapter:OpenCTIAdapter",
    "cyber-virustotal": "packages.providers.cyber-virustotal.adapter:VirusTotalAdapter",
    "cyber-abuseipdb": "packages.providers.cyber-abuseipdb.adapter:AbuseIPDBAdapter",
    "cyber-greynoise": "packages.providers.cyber-greynoise.adapter:GreyNoiseAdapter",
    "ml-huggingface": "packages.providers.ml-huggingface.adapter:HuggingFaceAdapter",
    "ml-labelstudio": "packages.providers.ml-labelstudio.adapter:LabelStudioAdapter",
    "ml-wandb": "packages.providers.ml-wandb.adapter:WandBAdapter",
    "ml-clearml": "packages.providers.ml-clearml.adapter:ClearMLAdapter",
    "ml-langfuse": "packages.providers.ml-langfuse.adapter:LangfuseAdapter",
}


class ProviderRegistry:
    """Runtime registry used by enrichment pipelines."""

    def __init__(self) -> None:
        self._providers: dict[str, Any] = {}

    def register(self, provider: Any) -> None:
        manifest = provider.get_manifest()
        self._providers[manifest.provider_id] = provider

    def get(self, provider_id: str) -> Any:
        return self._providers[provider_id]

    def register_default_cti_providers(self, mode: str = "airgapped") -> None:
        for provider_id, class_path in _PROVIDER_CLASS_PATHS.items():
            if not provider_id.startswith("cyber-"):
                continue
            module_path, class_name = class_path.split(":", 1)
            module = importlib.import_module(module_path)
            provider_cls = getattr(module, class_name)
            self._providers[provider_id] = provider_cls(mode=mode)

    def register_default_ml_providers(self, mode: str = "airgapped") -> None:
        for provider_id, class_path in _PROVIDER_CLASS_PATHS.items():
            if not provider_id.startswith("ml-"):
                continue
            module_path, class_name = class_path.split(":", 1)
            module = importlib.import_module(module_path)
            provider_cls = getattr(module, class_name)
            self._providers[provider_id] = provider_cls(mode=mode)

    def as_dict(self) -> dict[str, Any]:
        return dict(self._providers)
