"""Adapter for military-yolov5 sensor-fusion workflows.

Military/tactical context:
This wrapper standardizes local military-yolov5 execution so command systems can
fuse detections in sovereign and disconnected mission environments.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class MilitaryYolov5Adapter(IntegrationAdapter):
    """S3M sensor-fusion adapter for military-yolov5."""

    integration_id = "military-yolov5"
    domain = "sensor_fusion"
    _COMMAND_CANDIDATES = ('python3', 'yolo', 'yolov5')
    _DEFAULT_OPERATION = "detect_military_objects_in_video"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.sensor_fusion.military-yolov5")

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
        """Return integration metadata used for tactical sensor-fusion orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "military-yolov5"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/devavinothm/military-yolov5"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "YOLOv5 model family for military objects in surveillance video streams."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(raw.get("capabilities") or ['video_object_detection', 'weapon_detection', 'vehicle_detection']),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local runtime availability without external network dependencies."""
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
        """Execute adapter workflow with deterministic airgapped fixture fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise TypeError("params must be a dictionary")

        operation = request.get("operation", self._DEFAULT_OPERATION)
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 96:
            raise ValueError("operation must be a non-empty string with at most 96 characters")

        if self.is_airgapped:
            # Tactical requirement: deterministic fixture payloads support reproducible mission rehearsal.
            return {
                "status": "ok",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "available": False,
                "error": "military-yolov5 runtime is not installed or configured.",
                "fallback": self._read_fixture("sample_response.json"),
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
            "note": "Local YOLOv5 runtime detected; wrapper prepared for tactical video-object fusion.",
        }
