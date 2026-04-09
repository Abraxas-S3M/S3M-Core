"""Adapter for Captum attribution and interpretability workflows.

Military/tactical context:
Attribution outputs from mission models help commanders understand why an AI
assistant recommended a course of action, reducing decision ambiguity.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class CaptumAdapter(IntegrationAdapter):
    """Provide Captum availability checks and offline-safe execution outputs."""

    integration_id = "captum"
    domain = "hmi"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load Captum metadata for S3M integration catalog services."""
        raw: dict[str, Any] = {}
        manifest_path = self._manifest_path()
        if manifest_path.exists():
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                raw = loaded

        return IntegrationManifest(
            name=str(raw.get("name") or "Captum"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/pytorch/captum"),
            license=str(raw.get("license") or "BSD"),
            description=str(
                raw.get("description")
                or "Model interpretability and attribution library for PyTorch."
            ),
            integration_type="adapter",
            capabilities=[
                "feature_attribution",
                "layer_attribution",
                "mission_model_explanation_support",
            ],
            pip_dependencies=["captum"],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Check if Captum is locally installed for disconnected mission stacks."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        return importlib.util.find_spec("captum") is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run attribution task wrapper or deterministic fixture in airgapped mode."""
        params = params or {}
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if isinstance(fixture, dict):
                fixture["mode"] = "airgapped"
                fixture["integration_id"] = self.integration_id
                fixture["request"] = {
                    "operation": str(params.get("operation", "attribution_report")),
                    "method": str(params.get("method", "integrated_gradients")),
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
                "reason": "captum_not_installed",
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "mode": self.mode,
            "detail": "Captum is available locally for mission attribution workflows.",
        }
