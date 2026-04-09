"""Adapter for xai_resources curated explainability materials.

Military/tactical context:
Tactical AI governance requires a broad evidence base to justify model behavior
and maintain accountable human oversight in contested environments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class XaiResourcesAdapter(IntegrationAdapter):
    """Serve XAI resource collections for mission assurance workflows."""

    integration_id = "xai-resources"
    domain = "hmi"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Read manifest metadata for S3M orchestrator compatibility."""
        raw: dict[str, Any] = {}
        manifest_path = self._manifest_path()
        if manifest_path.exists():
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                raw = loaded

        return IntegrationManifest(
            name=str(raw.get("name") or "xai_resources"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/pbiecek/xai_resources"),
            license=str(raw.get("license") or "MIT"),
            description=str(raw.get("description") or "Collection of XAI papers, tools, and resources."),
            integration_type="reference",
            capabilities=[
                "xai_reference_collection",
                "operator_explainability_training_support",
                "assurance_artifact_preparation",
            ],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Check local mirror presence for sovereign offline execution."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        mirror_path = Path(
            self._env(
                "XAI_RESOURCES_PATH",
                default=str(Path(__file__).resolve().parent / "mirror"),
            )
        )
        return mirror_path.exists()

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return fixture-backed XAI resource bundles for HMI analysts."""
        params = params or {}
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if isinstance(fixture, dict):
                fixture["mode"] = "airgapped"
                fixture["integration_id"] = self.integration_id
                fixture["request"] = {
                    "operation": str(params.get("operation", "retrieve_xai_resources")),
                    "focus": str(params.get("focus", "model_transparency_training_pack")),
                }
                return fixture
            return {
                "status": "error",
                "reason": "fixture_not_found",
                "integration_id": self.integration_id,
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "reason": "xai_resources_mirror_not_found",
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "mode": self.mode,
            "detail": "Local xai_resources mirror detected for tactical explainability support.",
        }
