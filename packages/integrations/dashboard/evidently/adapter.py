"""Evidently adapter for tactical ML/LLM quality dashboard operations.

Military/tactical context:
This wrapper provides resilient quality-monitoring summaries for model outputs
so mission teams can detect drift, degradation, or unsafe behavior in local
dashboard workflows even without internet reach-back.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class EvidentlyAdapter(IntegrationAdapter):
    """S3M dashboard integration for Evidently monitoring telemetry."""

    integration_id = "evidently"
    domain = "dashboard"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self._manifest_path = Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load adapter metadata from manifest.yaml."""

        raw = yaml.safe_load(self._manifest_path.read_text(encoding="utf-8")) or {}
        return IntegrationManifest(
            name=str(raw.get("name", "Evidently")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/evidentlyai/evidently")),
            license=str(raw.get("license", "Apache 2.0")),
            description=str(
                raw.get(
                    "description",
                    "ML/LLM observability dashboard for evaluations, testing, and monitoring.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(raw.get("capabilities", ["drift_dashboard", "evaluation_monitoring", "quality_regression_detection"])),
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Check if Evidently tooling is available or fallback fixture exists."""

        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        return importlib.util.find_spec("evidently") is not None or shutil.which("evidently") is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return mission-oriented model-monitoring dashboard data."""

        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a mapping when provided")

        safe_params = dict(params or {})
        action = str(safe_params.get("action", "dashboard_summary")).strip().lower()
        if action not in {"dashboard_summary", "quality_snapshot", "drift_overview"}:
            raise ValueError("Unsupported action for evidently adapter")

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            self.logger.info("Returning airgapped fixture payload for action=%s", action)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "action": action,
                "result": fixture,
            }

        available = self.validate_availability()
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local_probe",
            "action": action,
            "available": available,
            "result": {
                "status": "ready" if available else "unavailable",
                "tooling": "evidently",
            },
        }

