"""BattleSimulator adapter for tactical unit behavior dashboards."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class BattlesimulatorAdapter(IntegrationAdapter):
    """Wraps BattleSimulator for mission rehearsal and after-action dashboards."""

    integration_id = "battlesimulator"
    domain = "dashboard"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("BattleSimulator manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load static integration metadata used by tactical service discovery."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "BattleSimulator"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/gregparkes/BattleSimulator"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Animated 2D battle visualizer for tactical behavior analysis in command dashboards."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[str(item) for item in raw.get("capabilities") or ["simulation_playback", "unit_timeline"]],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Confirm local BattleSimulator availability without using external network calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        install_path = self._env("BATTLESIMULATOR_PATH").strip()
        if install_path:
            return Path(install_path).expanduser().exists()

        return any(shutil.which(command) for command in ("battlesimulator", "battle-simulator"))

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return mission dashboard output, using fixture replay in airgapped deployments."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("BattleSimulator execute params must be a dictionary.")

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if not isinstance(fixture, dict) or not fixture:
                raise FileNotFoundError("Missing BattleSimulator fixture: sample_response.json")
            response = dict(fixture)
            response["mode"] = "airgapped"
            response["request"] = request
            return response

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "detail": "BattleSimulator binary or local checkout was not found.",
            }

        # Tactical safety constraint: online stub avoids uncontrolled external execution paths.
        return {
            "status": "deferred",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": "online",
            "request": request,
            "detail": "Local BattleSimulator execution is available but not wired in this wrapper revision.",
        }

