"""Adapter for awesome-c2 military adaptations interoperability resources.

Military/tactical context:
This wrapper provides command-and-control planners with a deterministic method
to access curated C2 interoperability references while operating on sovereign,
airgapped infrastructure.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeC2militaryAdaptationsAdapter(IntegrationAdapter):
    """Expose curated C2 adaptation resources with offline fixture fallback."""

    integration_id = "awesome-c2-military-adaptations"
    domain = "interop"

    _SUPPORTED_OPERATIONS = {"catalog", "topic_lookup", "capability_mapping"}
    _LOCAL_MIRROR_ENV = "AWESOME_C2_MILITARY_ADAPTATIONS_PATH"
    _FALLBACK_COMMAND = "git"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            return {}
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate request payloads for security-first C2 processing."""
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

        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Load orchestrator metadata from the wrapper manifest file."""
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "awesome-c2 (military adaptations)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "Search related awesome lists and forks"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Curated military C2 and interoperability resources for planning and adaptation."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities") or ["c2-resource-catalog", "interop-guidance", "capability-mapping"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Confirm local mirror or minimal tooling for C2 resource access."""
        if self.is_airgapped:
            fixture_payload = self._read_fixture("sample_response.json")
            return isinstance(fixture_payload, dict) and bool(fixture_payload)

        configured_path = self._env(self._LOCAL_MIRROR_ENV)
        if configured_path:
            return Path(configured_path).expanduser().exists()
        return shutil.which(self._FALLBACK_COMMAND) is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return curated C2 adaptation results or fixture data when airgapped."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "catalog").strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning offline fixture for tactical C2 interoperability planning.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "status": "ok",
                "operation": operation,
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        available = self.validate_availability()
        if not available:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "request": safe_params,
                "message": "No local awesome-c2 military adaptation mirror is available.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": safe_params,
            "message": "Runtime handoff prepared for local curated C2 adaptation indexing.",
        }
