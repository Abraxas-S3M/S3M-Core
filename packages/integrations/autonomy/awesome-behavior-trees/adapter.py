"""awesome-behavior-trees adapter for doctrine and reference curation.

Military/tactical context:
Behavior-tree doctrine, examples, and implementation references accelerate
autonomy playbook development for mission software teams in sovereign settings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeBehaviorTreesAdapter(IntegrationAdapter):
    """Adapter for behavior-tree reference indexing workflows."""

    integration_id = "awesome-behavior-trees"
    domain = "autonomy"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load manifest metadata used by S3M integration discovery."""
        raw: dict[str, Any] = {}
        manifest_path = self._manifest_path()
        if manifest_path.exists():
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                raw = loaded

        return IntegrationManifest(
            name=str(raw.get("name") or "awesome-behavior-trees"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url") or "https://github.com/BehaviorTree/awesome-behavior-trees"
            ),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Curated behavior-tree resources and examples for autonomy engineering."
            ),
            integration_type="adapter",
            capabilities=[
                "reference_catalog",
                "behavior_tree_training_resources",
                "autonomy_playbook_support",
            ],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Check for locally mirrored reference data in offline settings."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        mirror_path = Path(
            self._env(
                "AWESOME_BEHAVIOR_TREES_PATH",
                default=str(Path(__file__).resolve().parent / "mirror"),
            )
        )
        return mirror_path.exists()

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return curated behavior-tree references, fixture-backed when offline."""
        params = params or {}
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if isinstance(fixture, dict):
                fixture["mode"] = "airgapped"
                fixture["integration_id"] = self.integration_id
                fixture["request"] = {
                    "operation": str(params.get("operation", "list_behavior_tree_references")),
                    "topic": str(params.get("topic", "autonomy_control_logic")),
                }
                return fixture
            return {"status": "error", "reason": "fixture_not_found", "integration_id": self.integration_id}

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "reason": "reference_mirror_not_found",
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "mode": self.mode,
            "detail": "Local behavior-tree reference mirror detected and ready for indexing.",
        }
