"""Adapter for Border-Surveillance-System (variants) integration workflows.

Military/tactical context:
This wrapper supports sovereign sensor analytics operations where remote-sensing
workflows must run with deterministic behavior in contested or disconnected
environments.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class BorderSurveillanceSystemvariantsAdapter(IntegrationAdapter):
    """S3M adapter for Border-Surveillance-System (variants) sensor-analytics workflows."""

    integration_id = "border-surveillance-system-variants"
    domain = "sensor_analytics"
    _COMMAND_CANDIDATES = ('python3', 'opencv_version', 'git')
    _DEFAULT_OPERATION = "detect_border_anomalies"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.sensor_analytics.border-surveillance-system-variants")

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
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params.keys()):
            raise ValueError("params keys must be strings")
        try:
            return json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc

    def get_manifest(self) -> IntegrationManifest:
        """Return manifest metadata for tactical sensor-analytics discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Border-Surveillance-System (variants)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "Related forks of subhayudas/Border-Surveillance-System"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Variant wrappers for AI-powered border anomaly detection workflows with map and remote-sensing extensions."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ['perimeter_anomaly_detection', 'map_overlay_generation', 'cross_sensor_alert_fusion']
            ),
            system_dependencies=self._coerce_list(
                raw.get("system_dependencies")
                or ["python3"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local runtime prerequisites without using external API calls."""
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            return isinstance(fixture, dict) and bool(fixture)

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute core sensor-analytics wrapper logic with fixture fallback."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or self._DEFAULT_OPERATION)

        if self.is_airgapped:
            # Tactical requirement: deterministic fixture payloads enable reproducible mission rehearsal.
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
                "source": "runtime",
                "operation": operation,
                "request": request,
                "message": "Local runtime dependencies are unavailable for this integration.",
            }

        return {
            "status": "accepted",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "operation": operation,
            "request": request,
            "message": "Local readiness checks passed; orchestrator may proceed with controlled execution.",
        }
