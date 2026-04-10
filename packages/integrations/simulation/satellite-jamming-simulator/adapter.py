"""Adapter for satellite-jamming-simulator RF interference workflows.

Military/tactical context:
This wrapper supports space-denial rehearsal by validating and replaying
radio-frequency jamming scenario outputs in sovereign airgapped operations.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class SatelliteJammingSimulatorAdapter(IntegrationAdapter):
    """S3M simulation adapter for earth-to-space jamming simulation."""

    integration_id = "satellite-jamming-simulator"
    domain = "simulation"
    _COMMAND_CANDIDATES = ("satellite-jamming-simulator", "sat-jam-sim")
    _DEFAULT_OPERATION = "simulate_rfi_attack_window"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.simulation.satellite-jamming-simulator")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        path = self._manifest_path()
        if not path.exists():
            self.logger.warning("Manifest file missing: %s", path)
            return {}

        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", path)
            return {}

        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate EW simulation requests before execution."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")

        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc

        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Load metadata for EW and satellite-resilience mission planning."""
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "satellite-jamming-simulator"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/deptofdefense/satellite-jamming-simulator(archived"
            ),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Simulator for earth-to-space radio frequency interference and jamming attacks."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["rfi_attack_modeling", "uplink_resilience_assessment", "satcom_disruption_rehearsal"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies") or ["python3"]),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check whether local satellite-jamming simulator artifacts exist."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        sim_path = self._env("SATELLITE_JAMMING_SIMULATOR_PATH").strip()
        if sim_path:
            return Path(sim_path).expanduser().exists()

        sim_entry = self._env("SATELLITE_JAMMING_SIMULATOR_ENTRYPOINT").strip()
        if sim_entry:
            return Path(sim_entry).expanduser().is_file()

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute EW simulation with deterministic airgapped fixture fallback."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or self._DEFAULT_OPERATION).strip().lower()

        if self.is_airgapped:
            self.logger.info("Returning fixture data for operation=%s", operation)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "status": "ok",
                "operation": operation,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "request": request,
                "message": "satellite-jamming-simulator runtime is not installed or configured on this node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "ready",
            "operation": operation,
            "request": request,
            "message": "Satellite jamming simulator adapter is available for local EW rehearsal.",
        }
