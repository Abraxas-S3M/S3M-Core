"""Adapter for OpenMap references used in DIS/C2SIM operational displays.

Military/tactical context:
This wrapper supports mission map display interoperability by exposing
OpenMap-related references through a sovereign, deterministic adapter contract.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class OpenmaprelatedInDisAdapter(IntegrationAdapter):
    """Expose OpenMap-related DIS context data with fixture fallback."""

    integration_id = "openmap-related-in-dis-contexts"
    domain = "interop"

    _REPO_ENV_VAR = "OPENMAP_RELATED_IN_DIS_CONTEXTS_PATH"
    _COMMAND_CANDIDATES = ("java", "openmap")

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
        """Validate operator input used for tactical display workflows."""
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
        loaded = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}

    def get_manifest(self) -> IntegrationManifest:
        """Load metadata for coalition simulation display interoperability."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "OpenMap (related in DIS contexts)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "Search BBN OpenMap forks"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "OpenMap toolkit references for DIS/C2SIM geospatial display interoperability."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["map_rendering_reference", "dis_visualization_support", "c2sim_overlay_support"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check whether OpenMap prerequisites are locally available."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_path = self._env(self._REPO_ENV_VAR)
        if configured_path and Path(configured_path).expanduser().exists():
            return True
        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Wrap tactical map interoperability operation with fixture fallback."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or "display_profile_lookup")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning OpenMap-related fixture.")
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
                "OpenMap local runtime is available for coalition situational displays."
                if available
                else "Install OpenMap-compatible runtime or set OPENMAP_RELATED_IN_DIS_CONTEXTS_PATH."
            ),
        }
