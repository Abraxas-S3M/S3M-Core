"""Adapter for NETN references discovered in OpenC2SIM artifacts.

Military/tactical context:
This wrapper standardizes federation agreement metadata so coalition command
nodes can align DIS/C2SIM message semantics in contested environments.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class NetnReferencesInOpenc2simAdapter(IntegrationAdapter):
    """Expose NETN/OpenC2SIM federation references with fixture support."""

    integration_id = "netn-references-in-openc2sim"
    domain = "interop"

    _REPO_ENV_VAR = "NETN_REFERENCES_IN_OPENC2SIM_PATH"
    _COMMAND_CANDIDATES = ("git", "xmllint")

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
        """Validate federation request payloads for secure coalition handling."""
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
        """Load NETN/OpenC2SIM metadata for interoperability orchestration."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "NETN references in OpenC2SIM"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "Artifacts in OpenC2SIM repos"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "NETN federation agreement and extension references for NATO-aligned DIS/C2SIM workflows."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["federation_agreement_reference", "c2sim_extension_mapping", "interop_profile_alignment"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local NETN/OpenC2SIM artifact availability."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_path = self._env(self._REPO_ENV_VAR)
        if configured_path and Path(configured_path).expanduser().exists():
            return True
        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return federation reference output for tactical interop planning."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or "federation_reference_lookup")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning NETN/OpenC2SIM fixture.")
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
                "NETN/OpenC2SIM references are locally available for federation planning."
                if available
                else "Configure NETN_REFERENCES_IN_OPENC2SIM_PATH or install local XML tooling."
            ),
        }
