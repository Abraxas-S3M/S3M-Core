"""Adapter for awesome-xai reference workflows.

Military/tactical context:
Commanders need broad explainable AI method coverage to verify model trust
boundaries before integrating AI outputs into mission planning cycles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeXaiAdapter(IntegrationAdapter):
    """Expose curated XAI resources through a mission-safe adapter contract."""

    integration_id = "awesome-xai"
    domain = "hmi"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata for S3M orchestrator registry."""
        raw: dict[str, Any] = {}
        manifest_path = self._manifest_path()
        if manifest_path.exists():
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                raw = loaded

        return IntegrationManifest(
            name=str(raw.get("name") or "awesome-xai"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/altamiracorp/awesome-xai"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Curated list of XAI papers, methods, tools, and resources."
            ),
            integration_type="reference",
            capabilities=[
                "xai_landscape_mapping",
                "method_selection_support",
                "mission_model_assurance_reference",
            ],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Ensure local curated resource mirror exists for offline operations."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        mirror_path = Path(
            self._env(
                "AWESOME_XAI_PATH",
                default=str(Path(__file__).resolve().parent / "mirror"),
            )
        )
        return mirror_path.exists()

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return XAI resource recommendations for human-machine review teams."""
        params = params or {}
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if isinstance(fixture, dict):
                fixture["mode"] = "airgapped"
                fixture["integration_id"] = self.integration_id
                fixture["request"] = {
                    "operation": str(params.get("operation", "list_xai_resources")),
                    "mission_task": str(params.get("mission_task", "explainability_method_selection")),
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
                "reason": "xai_reference_mirror_not_found",
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "mode": self.mode,
            "detail": "Local awesome-xai mirror detected for mission assurance workflows.",
        }
