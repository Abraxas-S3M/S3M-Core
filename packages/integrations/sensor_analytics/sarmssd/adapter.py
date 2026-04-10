"""Adapter for SARMSSD SAR ship detection workflows.

Military/tactical context:
This wrapper exposes YOLO-based SAR ship-detection readiness checks that support
rapid maritime target screening in sovereign, disconnected ISR deployments.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class SarmssdAdapter(IntegrationAdapter):
    """S3M adapter for SARMSSD ship detection analytics."""

    integration_id = "sarmssd"
    domain = "sensor_analytics"
    _COMMAND_CANDIDATES = ("python3", "python", "yolo")
    _DEFAULT_OPERATION = "detect_ships_in_sar_frames"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.sensor_analytics.sarmssd")

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
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(raw, dict):
            self.logger.warning("Manifest content is not a mapping: %s", manifest_path)
            return {}
        return raw

    def get_manifest(self) -> IntegrationManifest:
        """Return metadata for tactical SAR ship-detection orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "SARMSSD")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/buyukkanber/SARMSSD")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "YOLO11-based SAR ship detection workflows with data enhancement for maritime monitoring.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._coerce_list(
                raw.get("capabilities", ["sar_ship_detection", "yolo_inference", "enhanced_training_data"])
            ),
            system_dependencies=self._coerce_list(raw.get("system_dependencies", ["python3"])),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local runtime readiness without any external API access."""
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            return isinstance(fixture, dict) and bool(fixture)

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN").strip()
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH").strip()
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute SAR ship detection request with deterministic fixture fallback."""
        if params is None:
            request: dict[str, Any] = {}
        elif not isinstance(params, dict):
            raise ValueError("params must be a dictionary for secure SAR ship detection.")
        else:
            request = params

        operation = str(request.get("operation", self._DEFAULT_OPERATION))
        if len(operation) > 128:
            raise ValueError("operation length exceeds maximum allowed size.")

        if self.is_airgapped:
            return {
                "status": "ok",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "available": True,
                "result": self._read_fixture("sample_response.json"),
                "request": request,
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "available": False,
                "error": "SARMSSD runtime dependencies are not installed or configured.",
                "request": request,
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "available": True,
            "request": request,
            "note": "SARMSSD checks passed for offline maritime ship-detection triage.",
        }
