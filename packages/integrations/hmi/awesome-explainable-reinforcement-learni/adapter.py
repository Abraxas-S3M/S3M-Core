"""Adapter for awesome-explainable-reinforcement-learning resources.

Military/tactical context:
Mission commanders require explainable reinforcement learning references to
audit agent behavior before fielding autonomous decision support.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeExplainableReinforcementLearningAdapter(IntegrationAdapter):
    """Provide offline-safe access to XRL reference catalogs."""

    integration_id = "awesome-explainable-reinforcement-learni"
    domain = "hmi"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load registry metadata for mission planner integration discovery."""
        raw: dict[str, Any] = {}
        manifest_path = self._manifest_path()
        if manifest_path.exists():
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                raw = loaded

        return IntegrationManifest(
            name=str(raw.get("name") or "awesome-explainable-reinforcement-learning"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/Plankson/awesome-explainable-reinforcement-learning"
            ),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Curated resources and survey material for explainable reinforcement learning."
            ),
            integration_type="reference",
            capabilities=[
                "xrl_reference_curation",
                "operator_model_transparency_briefing",
                "mission_policy_explainability_support",
            ],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Validate local mirror availability for disconnected tactical operations."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        mirror_path = Path(
            self._env(
                "AWESOME_EXPLAINABLE_REINFORCEMENT_LEARNING_PATH",
                default=str(Path(__file__).resolve().parent / "mirror"),
            )
        )
        return mirror_path.exists()

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return XRL references, fixture-backed for airgapped deployments."""
        params = params or {}
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if isinstance(fixture, dict):
                fixture["mode"] = "airgapped"
                fixture["integration_id"] = self.integration_id
                fixture["request"] = {
                    "operation": str(params.get("operation", "list_xrl_resources")),
                    "focus_area": str(params.get("focus_area", "policy_explainability")),
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
                "reason": "xrl_reference_mirror_not_found",
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "mode": self.mode,
            "detail": "Local XRL reference mirror detected for mission explainability review.",
        }
