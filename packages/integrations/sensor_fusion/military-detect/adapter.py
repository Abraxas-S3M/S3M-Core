"""Adapter for Military-Detect remote sensing targeting workflows.

Military/tactical context:
This wrapper provides controlled access to remote-sensing military target
detection outputs (airbase, bridge, missile, warship) for mission planning in
sovereign and disconnected command networks.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class MilitaryDetectAdapter(IntegrationAdapter):
    """S3M adapter for Military-Detect inference and review workflows."""

    integration_id = "military-detect"
    domain = "sensor_fusion"
    _COMMAND_CANDIDATES = ("python3", "torchrun", "yolo")
    _DEFAULT_OPERATION = "remote_target_detection"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.sensor_fusion.military-detect")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}
        try:
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(loaded, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return loaded

    def get_manifest(self) -> IntegrationManifest:
        """Return manifest metadata for tactical sensor-fusion orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Military-Detect"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/Erichen911/Military-Detect"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Remote-sensing military target detection for fixed and maritime assets."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["airbase_detection", "bridge_detection", "warship_detection", "missile_site_detection"]
            ),
            system_dependencies=self._coerce_list(raw.get("system_dependencies") or ["python3"]),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local runtime availability without making network calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute target-detection wrapper with deterministic airgapped fallback."""
        if params is None:
            request: dict[str, Any] = {}
        elif not isinstance(params, dict):
            raise ValueError("params must be a dictionary for secure tactical sensor-fusion tasks.")
        else:
            request = params

        operation = request.get("operation", self._DEFAULT_OPERATION)
        if not isinstance(operation, str) or not operation.strip():
            raise ValueError("operation must be a non-empty string")

        if self.is_airgapped:
            # Tactical requirement: deterministic fixtures support auditable mission rehearsal.
            return {
                "status": "ok",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "available": True,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "runtime",
                "operation": operation,
                "available": False,
                "request": request,
                "error": "Military-Detect dependencies are not installed or configured.",
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "operation": operation,
            "available": True,
            "request": request,
            "note": "Military-Detect runtime prerequisites validated for local mission inference.",
        }
