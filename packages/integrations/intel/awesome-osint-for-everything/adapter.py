"""Awesome-OSINT-For-Everything adapter for S3M intelligence operations.

Military/tactical context:
This wrapper exposes a curated OSINT tool index so planners can rapidly map
collection options during mission preparation without internet connectivity.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeOsintForEverythingAdapter(IntegrationAdapter):
    """Wrap curated OSINT catalog workflows with deterministic fixture support."""

    integration_id = "awesome-osint-for-everything"
    domain = "intel"
    _SUPPORTED_OPERATIONS = {"catalog_lookup", "domain_scan", "tool_recommendation"}

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.intel.awesome-osint-for-everything")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            return {}
        loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate untrusted payloads before tactical query handling."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if len(params) > 128:
            raise ValueError("params contains too many top-level fields")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")

        safe_payload = json.loads(json.dumps(params))
        if len(json.dumps(safe_payload)) > 20000:
            raise ValueError("params payload is too large")
        return safe_payload

    def get_manifest(self) -> IntegrationManifest:
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "Awesome-OSINT-For-Everything"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url") or "https://github.com/Astrosp/Awesome-OSINT-For-Everything"
            ),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Broad collection of OSINT tools across domains."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["osint_tool_catalog", "domain_mapping", "collection_planning"]
            ),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_str_list(raw.get("system_dependencies") or ["python3"]),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        return any(shutil.which(command) for command in ("awesome-osint-for-everything", "python3"))

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute catalog-query wrapper with fixture fallback for offline ops."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "catalog_lookup").strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning fixture-backed OSINT catalog response for disconnected planning.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "source": "fixture",
                "available": True,
                "status": "ok",
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        availability = self.validate_availability()
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "source": "runtime",
            "available": availability,
            "status": "ready" if availability else "unavailable",
            # Sovereign policy: no direct internet access in wrapper runtime path.
            "message": "Runtime dependency check complete; external invocation is disabled by policy.",
            "request": safe_params,
        }
