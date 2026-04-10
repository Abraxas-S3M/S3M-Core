"""Adapter for RelaySMS-Android secure messaging relay workflows.

Military/tactical context:
This wrapper preserves low-bandwidth command messaging continuity over SMS
relay channels when internet transport is denied in contested theaters.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class RelaysmsAndroidAdapter(IntegrationAdapter):
    """S3M secure communications adapter for RelaySMS-Android."""

    integration_id = "relaysms-android"
    domain = "comms"
    _COMMAND_CANDIDATES = ("adb", "relay-sms", "gradle")
    _DEFAULT_OPERATION = "relay_delivery_status"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.comms.relaysms-android")

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
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return raw

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata for disconnected SMS relay operations."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "RelaySMS-Android"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/smswithoutborders/SMSwithoutBorders-Android"
            ),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Secure SMS relay adapter for denied-network tactical message continuity."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["sms_relay_delivery", "low_bandwidth_fallback", "offline_message_queuing"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local RelaySMS runtime/toolchain availability without network calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_").replace(".", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute secure relay wrapper with deterministic airgapped fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise TypeError("params must be a dictionary")

        operation = request.get("operation", self._DEFAULT_OPERATION)
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")

        if self.is_airgapped:
            # Tactical requirement: deterministic comms outputs support audit replay.
            return {
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
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "operation": operation,
                "error": "RelaySMS-Android runtime is not installed or configured",
                "fallback": self._read_fixture("sample_response.json"),
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "source": "local-runtime",
            "operation": operation,
            "request": request,
            "note": "Local secure relay tooling detected; external API calls remain disabled by policy.",
        }
