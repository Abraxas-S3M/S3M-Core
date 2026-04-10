"""Adapter for geoai geospatial intelligence workflows.

Military/tactical context:
This wrapper supports geospatial AI tasking for satellite scene processing,
segmentation, and fusion in sovereign deployments where external APIs are
forbidden.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class GeoaiAdapter(IntegrationAdapter):
    """S3M adapter for geoai remote-sensing analytics."""

    integration_id = "geoai"
    domain = "sensor_analytics"
    _COMMAND_CANDIDATES = ("python3", "python")
    _DEFAULT_OPERATION = "run_geospatial_segmentation_and_fusion"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.sensor_analytics.geoai")

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
        """Return metadata for tactical geospatial analytics orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "geoai")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/opengeos/geoai")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "AI for geospatial data processing including satellite segmentation and data fusion.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._coerce_list(
                raw.get("capabilities", ["satellite_processing", "semantic_segmentation", "geospatial_fusion"])
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
        """Execute geospatial analytics request with deterministic fixture fallback."""
        if params is None:
            request: dict[str, Any] = {}
        elif not isinstance(params, dict):
            raise ValueError("params must be a dictionary for secure geospatial analytics.")
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
                "error": "geoai runtime dependencies are not installed or configured.",
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
            "note": "geoai checks passed for disconnected geospatial intelligence workflows.",
        }
