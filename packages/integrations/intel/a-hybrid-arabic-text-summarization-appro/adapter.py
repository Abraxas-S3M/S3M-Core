"""Adapter for A-Hybrid-Arabic-Text-Summarization-Approach-based-on-Transformers.

Military/tactical context:
This wrapper supports hybrid extractive/abstractive condensation of Arabic
intelligence feeds, enabling rapid tactical brief generation on sovereign nodes.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AHybridArabicTextAdapter(IntegrationAdapter):
    """S3M adapter for hybrid Arabic transformer summarization workflows."""

    integration_id = "a-hybrid-arabic-text-summarization-appro"
    domain = "intel"
    _REPO_ENV_VAR = "A_HYBRID_ARABIC_TEXT_SUMMARIZATION_APPRO_PATH"
    _MODULE_CANDIDATES = ("transformers", "torch", "nltk")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate summarization task parameters for secure edge processing."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if len(params) > 128:
            raise ValueError("params contains too many top-level fields")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc
        if len(json.dumps(normalized)) > 50000:
            raise ValueError("params payload is too large")
        return normalized

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}
        try:
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(loaded, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return loaded

    def get_manifest(self) -> IntegrationManifest:
        """Load manifest metadata for intel integration discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "A-Hybrid-Arabic-Text-Summarization-Approach-based-on-Transformers")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(
                raw.get(
                    "source_url",
                    "https://github.com/mohamedehab00/A-Hybrid-Arabic-Text-Summarization-Approach-based-on-Transformers",
                )
            ),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "Hybrid extractive/abstractive Arabic text summarization using transformer architectures.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._coerce_list(
                raw.get("capabilities", ["hybrid_summarization", "arabic_briefing_support", "offline_transformer_runtime"])
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies", ["transformers", "torch", "nltk"])),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path", "")),
        )

    def validate_availability(self) -> bool:
        """Check if local hybrid summarization runtime is present."""
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            return isinstance(fixture, dict) and bool(fixture)

        configured_path = self._env(self._REPO_ENV_VAR)
        if configured_path:
            candidate = Path(configured_path).expanduser()
            if candidate.exists():
                return True

        local_mirror = Path(f"/opt/s3m/integrations/intel/{self.integration_id}")
        if local_mirror.exists():
            return True

        return any(importlib.util.find_spec(module_name) is not None for module_name in self._MODULE_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute hybrid summarization wrapper with deterministic fixture fallback."""
        request = self._sanitize_params(params)
        if self.is_airgapped:
            self.logger.info("Airgapped mode enabled; returning hybrid Arabic summarization fixture.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "local-wrapper",
                "status": "unavailable",
                "error": "Hybrid Arabic summarization runtime not configured locally",
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local-wrapper",
            "status": "ready",
            "operation": str(request.get("operation", "hybrid_summarize")),
            "request": request,
            "note": "Local hybrid Arabic summarization runtime is available for tactical briefing preparation.",
        }
