"""JSBSim adapter for tactical flight-projection dashboard operations.

Military/tactical context:
This wrapper enables S3M mission dashboards to surface aircraft dynamics and
projection snapshots using deterministic local simulation signals, including
offline fallback during denied-connectivity exercises.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class JsbsimAdapter(IntegrationAdapter):
    """S3M dashboard integration for JSBSim-derived telemetry."""

    integration_id = "jsbsim"
    domain = "dashboard"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self._manifest_path = Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load adapter metadata from manifest.yaml."""

        raw = yaml.safe_load(self._manifest_path.read_text(encoding="utf-8")) or {}
        return IntegrationManifest(
            name=str(raw.get("name", "JSBSim")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/JSBSim-Team/jsbsim")),
            license=str(raw.get("license", "LGPL-2.1")),
            description=str(
                raw.get(
                    "description",
                    "Flight dynamics simulator with projection dashboards for mission rehearsal and trajectory risk.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(raw.get("capabilities", ["flight_projection", "trajectory_dashboard", "sim_state_monitoring"])),
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Check if JSBSim is locally installable or fixture-backed."""

        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))
        return importlib.util.find_spec("jsbsim") is not None or shutil.which("jsbsim") is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Provide dashboard-ready JSBSim simulation insights."""

        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a mapping when provided")

        safe_params = dict(params or {})
        action = str(safe_params.get("action", "dashboard_summary")).strip().lower()
        if action not in {"dashboard_summary", "projection_snapshot", "flight_health"}:
            raise ValueError("Unsupported action for jsbsim adapter")

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
                "tooling": "jsbsim",
            },
        }

