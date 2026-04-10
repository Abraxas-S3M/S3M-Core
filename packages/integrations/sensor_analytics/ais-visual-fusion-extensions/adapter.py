"""Adapter for AIS-Visual-Fusion extension workflows.

Military/tactical context:
This wrapper supports maritime command-and-control by fusing AIS telemetry,
video tracks, and satellite cues for multi-view vessel tracking in offline ops.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AisVisualFusionExtensionsAdapter(IntegrationAdapter):
    """S3M adapter for AIS-Visual-Fusion extension workflows."""

    integration_id = "ais-visual-fusion-extensions"
    domain = "sensor_analytics"
    _COMMAND_CANDIDATES = ("python3", "ffmpeg")
    _DEFAULT_OPERATION = "fuse_multi_view_vessel_tracks"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger(
            "s3m.integrations.sensor_analytics.ais-visual-fusion-extensions"
        )

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

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
            self.logger.warning("Manifest content is not a mapping: %s", manifest_path)
            return {}
        return loaded

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary for secure multi-view vessel fusion.")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        try:
            return json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc

    def get_manifest(self) -> IntegrationManifest:
        """Return manifest metadata for multi-view maritime fusion support."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "AIS-Visual-Fusion extensions"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "Extensions of QuJX/AIS-Visual-Fusion"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Extensions for multi-view vessel fusion using AIS, video, and satellite cues."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=list(
                raw.get("capabilities")
                or [
                    "multi_view_track_fusion",
                    "ais_video_satellite_alignment",
                    "maritime_common_operating_picture_updates",
                ]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local fusion runtime readiness without network usage."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH").strip()
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_bin = self._env(f"{env_prefix}_BIN").strip()
        if configured_bin and shutil.which(configured_bin):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute fusion wrapper logic with deterministic airgapped fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or self._DEFAULT_OPERATION).strip()
        if not operation or len(operation) > 64:
            raise ValueError("operation must be a non-empty string up to 64 characters")

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "ok",
                "source": "fixture",
                "operation": operation,
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "source": "runtime",
                "operation": operation,
                "request": safe_params,
                "message": "AIS-Visual-Fusion extension runtime dependencies are not installed or configured.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "source": "runtime",
            "operation": operation,
            "request": safe_params,
            "message": "Local multi-view fusion runtime detected; mission pipeline can proceed under orchestrator control.",
        }
