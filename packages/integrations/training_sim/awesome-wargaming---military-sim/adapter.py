"""Adapter for awesome-wargaming and military-sim curated references.

Military/tactical context:
This wrapper enables curation pipelines to track sovereign-approved open-source
wargaming references used by doctrinal training teams in disconnected theaters.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeWargamingMilitaryAdapter(IntegrationAdapter):
    """S3M adapter for curated wargaming and military simulation reference lists."""

    integration_id = "awesome-wargaming---military-sim"
    domain = "training_sim"
    _COMMAND_CANDIDATES = ("python3", "git")
    _ENV_PATH_KEYS = ("AWESOME_WARGAMING_MILITARY_SIM_PATH", "AWESOME_WARGAMING_MILITARY_SIM_ROOT")
    _DEFAULT_OPERATION = "curated_reference_snapshot"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.training_sim.awesome-wargaming---military-sim")

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
        """Validate curated-list requests before tactical reference distribution."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc
        if len(json.dumps(normalized)) > 25000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "awesome-wargaming / military-sim"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "Search related awesome lists and military-sim topics"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Curated references for open-source wargaming and military training simulators."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["reference_discovery", "tooling_catalog", "training_stack_curated_lists"]
            ),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_str_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local availability of curated awesome-list artifacts."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_paths = [self._env(key).strip() for key in self._ENV_PATH_KEYS]
        if any(path and Path(path).expanduser().exists() for path in configured_paths):
            return True

        return any(shutil.which(command) is not None for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute curated list wrapper behavior with deterministic fixture fallback."""
        try:
            safe_params = self._sanitize_params(params)
        except ValueError as exc:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": str(exc),
            }

        operation = str(safe_params.get("operation") or self._DEFAULT_OPERATION).strip().lower()
        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning awesome-wargaming fixture payload.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "request": safe_params,
                "message": "Curated wargaming references are not installed on this sovereign node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "Curated wargaming references are available for local training workflows.",
        }
