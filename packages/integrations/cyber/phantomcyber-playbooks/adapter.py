"""Phantomcyber playbooks integration adapter.

Military/tactical context:
This adapter models SOAR playbook selection for cyber incident actions during
mission operations where orchestration decisions must remain offline-capable.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class PhantomcyberplaybooksAdapter(IntegrationAdapter):
    """Wrap playbook metadata and recommendation flows for S3M."""

    integration_id = "phantomcyber-playbooks"
    domain = "cyber"
    _SUPPORTED_OPERATIONS = {"list_playbooks", "recommend_playbook", "plan_response"}

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            return {}
        loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}

    def get_manifest(self) -> IntegrationManifest:
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "phantomcyber/playbooks"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Unknown"),
            description="SOAR playbook adapter for tactical cyber response orchestration.",
            integration_type="adapter",
            capabilities=["playbook-selection", "response-orchestration", "incident-automation"],
            system_dependencies=["phantom", "soarctl"],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        repo_path = self._env("PHANTOM_PLAYBOOKS_PATH")
        local_repo_exists = bool(repo_path) and Path(repo_path).exists()
        local_tools_exist = any(shutil.which(command) for command in ("phantom", "soarctl"))
        return local_repo_exists or local_tools_exist

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute playbook wrapper operation using fixture in airgapped mode."""
        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a dictionary when provided")

        request = params or {}
        operation = str(request.get("operation", "recommend_playbook")).strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning airgapped playbook recommendation fixture for operator review.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "source": "fixture",
                "result": self._read_fixture("sample_response.json"),
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "source": "runtime",
            "available": self.validate_availability(),
            "result": {
                "status": "simulated",
                "detail": "Playbook execution is represented locally; no external SOAR endpoint calls are made.",
            },
        }
