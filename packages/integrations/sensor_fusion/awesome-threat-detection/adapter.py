"""Adapter for Awesome Threat Detection resources in S3M sensor fusion.

Military/tactical context:
This wrapper provides deterministic access to threat-hunting reference content
for mission cyber-defense cells operating in disconnected or contested networks.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeThreatDetectionAdapter(IntegrationAdapter):
    """S3M integration adapter for awesome-threat-detection."""

    integration_id = "awesome-threat-detection"
    domain = "sensor_fusion"
    _DEFAULT_OPERATION = "threat_detection_catalog_query"
    _SUPPORTED_OPERATIONS = {
        "threat_detection_catalog_query",
        "suricata_zeek_extension_lookup",
        "hunting_playbook_seed",
    }
    _COMMAND_CANDIDATES = ("python3", "git")
    _LOCAL_PATH_ENV = "AWESOME_THREAT_DETECTION_PATH"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}
        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Unable to parse manifest YAML: %s", manifest_path)
            return {}
        return raw if isinstance(raw, dict) else {}

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
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        try:
            sanitized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc
        return sanitized

    def get_manifest(self) -> IntegrationManifest:
        """Return integration metadata consumed by S3M orchestrators."""
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "awesome-threat-detection"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url") or "https://github.com/0x4D31/awesome-threat-detection"
            ),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Curated threat detection and hunting resources including Suricata/Zeek ML extensions."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or [
                    "threat-hunting-catalog-curation",
                    "suricata-zeek-ml-reference-discovery",
                    "sensor-fusion-detection-playbook-support",
                ]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local availability without using external network calls."""
        if self.is_airgapped:
            payload = self._read_fixture("sample_response.json")
            return isinstance(payload, dict) and bool(payload)

        configured_path = self._env(self._LOCAL_PATH_ENV)
        if configured_path:
            return Path(configured_path).expanduser().exists()

        return any(shutil.which(command) is not None for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper with deterministic fixture behavior in airgapped mode."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or self._DEFAULT_OPERATION).strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            # Tactical cyber drills require reproducible outputs while disconnected.
            return {
                "status": "ok",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "available": True,
                "data": self._read_fixture("sample_response.json"),
                "request": safe_params,
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "operation": operation,
                "available": False,
                "error": "awesome-threat-detection resources are not configured on this node.",
                "request": safe_params,
            }

        return {
            "status": "ready",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "operation": operation,
            "available": True,
            "request": safe_params,
            "note": "awesome-threat-detection adapter is ready to support local threat-hunting reference workflows.",
        }
