"""Adapter for awesome-geospatial curated interoperability references.

Military/tactical context:
This wrapper helps coalition simulation operators discover trusted geospatial
and DIS/C2SIM-aligned tooling from a local sovereign environment.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeGeospatialAdapter(IntegrationAdapter):
    """Expose awesome-geospatial data with airgapped fixture fallback."""

    integration_id = "awesome-geospatial"
    domain = "interop"

    _REPO_ENV_VAR = "AWESOME_GEOSPATIAL_PATH"
    _COMMAND_CANDIDATES = ("ogrinfo", "gdalinfo", "qgis")

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
        """Validate mission input to reduce malformed task injection risk."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        if len(params) > 128:
            raise ValueError("params contains too many top-level fields")
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc
        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large")
        return normalized

    def _load_manifest(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}
        loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}

    def get_manifest(self) -> IntegrationManifest:
        """Load tactical metadata required by S3M orchestration layers."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "awesome-geospatial"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/sacridini/Awesome-Geospatial"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Curated geospatial and simulation tooling references for DIS/C2SIM planning cells."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities") or ["geospatial_catalog", "dis_c2sim_support", "planning_reference"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local mirror or geospatial toolchain presence for mission use."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_path = self._env(self._REPO_ENV_VAR)
        if configured_path and Path(configured_path).expanduser().exists():
            return True
        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute adapter action with deterministic airgapped behavior."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or "catalog_lookup")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning awesome-geospatial fixture.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        available = self.validate_availability()
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local-wrapper",
            "operation": operation,
            "available": available,
            "status": "ready" if available else "unavailable",
            "request": request,
            "detail": (
                "Local geospatial interoperability references are ready for mission rehearsal."
                if available
                else "Install geospatial tooling or configure AWESOME_GEOSPATIAL_PATH."
            ),
        }
