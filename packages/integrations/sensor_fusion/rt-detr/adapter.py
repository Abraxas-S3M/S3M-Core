"""Adapter for RT-DETR tactical transformer detection workflows.

Military/tactical context:
This wrapper enables deterministic readiness checks for transformer-based
real-time detection in mission loops where precision/latency tradeoffs matter.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class RtDetrAdapter(IntegrationAdapter):
    """S3M adapter for rt-detr detection workflows."""

    integration_id = "rt-detr"
    domain = "sensor_fusion"
    _DEFAULT_OPERATION = "transformer_detection_pass"
    _MODULE_CANDIDATES = ("torch", "cv2")
    _COMMAND_CANDIDATES = ("python3",)

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.sensor_fusion.rt-detr")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

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
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def get_manifest(self) -> IntegrationManifest:
        """Return manifest metadata for tactical transformer detection orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "RT-DETR")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/lyuwenyu/RT-DETR")),
            license=str(raw.get("license", "Apache 2.0")),
            description=str(
                raw.get(
                    "description",
                    "Official Real-Time Detection Transformer focused on strong speed/accuracy tradeoffs.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._coerce_list(
                raw.get(
                    "capabilities",
                    ["real_time_transformer_detection", "precision_latency_optimization", "edge_deployment_readiness"],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local RT-DETR runtime prerequisites without network access."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        modules_ready = any(importlib.util.find_spec(name) is not None for name in self._MODULE_CANDIDATES)
        commands_ready = any(shutil.which(command) is not None for command in self._COMMAND_CANDIDATES)
        return modules_ready or commands_ready

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper request with deterministic airgapped fixture mode."""
        if params is None:
            request: dict[str, Any] = {}
        elif not isinstance(params, dict):
            raise ValueError(
                "params must be a dictionary for secure tactical RT-DETR execution."
            )
        else:
            request = params

        operation = str(request.get("operation", self._DEFAULT_OPERATION))
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
                "error": "RT-DETR dependencies are not installed or configured.",
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
            "note": "RT-DETR checks passed for tactical transformer-detection readiness.",
        }
