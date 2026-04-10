"""Adapter for YOLOV8_SAR_SHIP_DETECTION oriented SAR vessel detection.

Military/tactical context:
This wrapper supports maritime reconnaissance by producing oriented bounding
boxes that better represent vessel heading and deck footprint in SAR imagery.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class Yolov8SarShipDetectionAdapter(IntegrationAdapter):
    """S3M adapter for YOLOv8-OBB SAR ship detection workflows."""

    integration_id = "yolov8-sar-ship-detection"
    domain = "sensor_analytics"
    _COMMAND_CANDIDATES = ("python3", "yolo", "ultralytics")
    _DEFAULT_OPERATION = "detect_sar_ships_obb"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger(
            "s3m.integrations.sensor_analytics.yolov8-sar-ship-detection"
        )

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

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise TypeError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        try:
            return json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc

    def get_manifest(self) -> IntegrationManifest:
        """Load metadata required for SAR OBB target detection orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "YOLOV8_SAR_SHIP_DETECTION"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/sethubolt7/YOLOV8_SAR_SHIP_DETECTION"
            ),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Production-grade YOLOv8-OBB with Lee speckle filtering for SAR ship detection."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["sar_obb_detection", "speckle_filtered_inference", "vessel_heading_estimation"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local runtime availability without external network access."""
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
        """Run oriented SAR ship detection with deterministic fixture fallback."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or self._DEFAULT_OPERATION)

        if self.is_airgapped:
            # Tactical requirement: fixed offline payloads enable repeatable battle-lab scoring.
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "ok",
                "source": "fixture",
                "operation": operation,
                "request": request,
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
                "request": request,
                "message": "YOLOV8_SAR_SHIP_DETECTION runtime dependencies are not installed or configured.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "accepted",
            "source": "runtime",
            "operation": operation,
            "request": request,
            "message": "Local YOLOv8 SAR OBB readiness checks passed; execution remains orchestrator-governed.",
        }
