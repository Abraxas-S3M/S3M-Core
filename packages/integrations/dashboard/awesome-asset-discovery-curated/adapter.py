"""Dashboard integration adapter for Awesome-Asset-Discovery (Curated)."""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeAssetDiscoverycuratedAdapter(IntegrationAdapter):
    """Provide tactical dashboard access with safe airgapped fallback behavior."""

    integration_id = "awesome-asset-discovery-curated"
    domain = "dashboard"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        # Tactical operations require a deterministic logger namespace for audit traces.
        self.logger = logging.getLogger("s3m.integrations.dashboard.awesome-asset-discovery-curated")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load repository metadata used by mission orchestration and compliance checks."""
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("Manifest must be a key-value mapping.")

        return IntegrationManifest(
            name=str(raw_manifest.get("name") or "Awesome-Asset-Discovery (Curated)"),
            slug=str(raw_manifest.get("slug") or self.integration_id),
            domain=str(raw_manifest.get("domain") or self.domain),
            source_url=str(raw_manifest.get("source_url") or "https://github.com/redhuntlabs/Awesome-Asset-Discovery"),
            license=str(raw_manifest.get("license") or "MIT"),
            description="Curated dashboard resources for asset discovery and exposure triage in defensive cyber operations.",
            integration_type="adapter",
            capabilities=[
    "asset_discovery_catalog",
    "exposure_triage",
    "dashboard_curation",
            ],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Check local runtime presence without making external calls."""
        if self.is_airgapped:
            return True

        runtime_candidates = ["git", "python3"]
        is_available = any(shutil.which(command) for command in runtime_candidates)
        if not is_available:
            self.logger.warning(
                "No supported runtime found for %s. Checked: %s",
                self.integration_id,
                runtime_candidates,
            )
        return is_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a local wrapper action for tactical dashboard ingestion."""
        safe_params = params or {}
        if not isinstance(safe_params, dict):
            raise TypeError("params must be a dictionary.")

        action = safe_params.get("action", "overview")
        if not isinstance(action, str) or not action.strip() or len(action) > 64:
            raise ValueError("action must be a non-empty string with at most 64 characters.")

        if self.is_airgapped:
            fixture_payload = self._read_fixture("sample_response.json")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "action": action,
                "data": fixture_payload,
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "error": "runtime_unavailable",
                "detail": "Required runtime is not installed on this tactical node.",
            }

        # Online mode intentionally remains local-only to preserve sovereign/offline security guarantees.
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local-runtime",
            "action": action,
            "status": "ready",
            "detail": "Runtime detected; external network execution is disabled by policy.",
        }
