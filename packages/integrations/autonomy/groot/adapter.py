"""Groot adapter for behavior-tree mission planning support.

Military/tactical context:
Behavior trees are used to encode deterministic autonomy logic for mission
execution. This wrapper enables offline-safe access to Groot design and review
signals for tactical autonomy teams.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class GrootAdapter(IntegrationAdapter):
    """Adapter for BehaviorTree Groot authoring and diagnostics workflows."""

    integration_id = "groot"
    domain = "autonomy"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Return integration metadata loaded from manifest.yaml."""
        raw: dict[str, Any] = {}
        manifest_path = self._manifest_path()
        if manifest_path.exists():
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                raw = loaded

        return IntegrationManifest(
            name=str(raw.get("name") or "Groot"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/BehaviorTree/Groot"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Graphical editor for creating, monitoring, and debugging behavior trees."
            ),
            integration_type="adapter",
            capabilities=[
                "behavior_tree_authoring",
                "behavior_tree_monitoring",
                "autonomy_debugging",
            ],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Check for local Groot executable presence."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        return any(shutil.which(cmd) is not None for cmd in ("groot", "groot2", "groot_app"))

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Wrap behavior-tree tooling operations with offline fallback."""
        params = params or {}
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if isinstance(fixture, dict):
                fixture["mode"] = "airgapped"
                fixture["integration_id"] = self.integration_id
                fixture["request"] = {
                    "operation": str(params.get("operation", "validate_behavior_tree")),
                    "tree_name": str(params.get("tree_name", "recon_patrol_tree")),
                }
                return fixture
            return {"status": "error", "reason": "fixture_not_found", "integration_id": self.integration_id}

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "reason": "groot_executable_not_found",
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "mode": self.mode,
            "detail": "Groot executable detected; invoke local BT authoring pipeline for live interaction.",
        }
