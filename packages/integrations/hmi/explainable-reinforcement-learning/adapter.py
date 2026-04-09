"""Adapter for explainable-reinforcement-learning research resources.

Military/tactical context:
Human-machine teams must cross-check reinforcement learning policy rationale
against doctrine and legal constraints before operational deployment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class ExplainableReinforcementLearningAdapter(IntegrationAdapter):
    """Provide deterministic access to XRL paper and method references."""

    integration_id = "explainable-reinforcement-learning"
    domain = "hmi"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load metadata required by S3M integration discovery."""
        raw: dict[str, Any] = {}
        manifest_path = self._manifest_path()
        if manifest_path.exists():
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                raw = loaded

        return IntegrationManifest(
            name=str(raw.get("name") or "explainable-reinforcement-learning"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/observer4599/explainable-reinforcement-learning"
            ),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Repository of explainable reinforcement learning papers and resources."
            ),
            integration_type="reference",
            capabilities=[
                "xrl_paper_indexing",
                "doctrinal_explainability_research_support",
                "operator_review_packet_generation",
            ],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Check for a local mirror suitable for classified deployments."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        mirror_path = Path(
            self._env(
                "EXPLAINABLE_REINFORCEMENT_LEARNING_PATH",
                default=str(Path(__file__).resolve().parent / "mirror"),
            )
        )
        return mirror_path.exists()

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return paper-centric XRL references with offline fixture fallback."""
        params = params or {}
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if isinstance(fixture, dict):
                fixture["mode"] = "airgapped"
                fixture["integration_id"] = self.integration_id
                fixture["request"] = {
                    "operation": str(params.get("operation", "query_xrl_papers")),
                    "topic": str(params.get("topic", "human_interpretable_policy_analysis")),
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
                "reason": "xrl_repository_mirror_not_found",
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "mode": self.mode,
            "detail": "Local XRL research mirror detected for operator review workflows.",
        }
