"""Adapter for enchat secure relay communication workflows.

Military/tactical context:
This wrapper standardizes ephemeral encrypted relay-chat telemetry so tactical
units can validate secure comms readiness while operating in disconnected and
contested electromagnetic environments.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class EnchatextensionsAdapter(IntegrationAdapter):
    """S3M adapter for enchat relay-mediated encrypted terminal messaging."""

    integration_id = "enchat-extensions"
    domain = "comms"
    _COMMAND_CANDIDATES = ("enchat", "enchat-cli")
    _DEFAULT_OPERATION = "relay_status"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        # Tactical requirement: keep stable logger namespace for mission audits.
        self.logger = logging.getLogger("s3m.integrations.comms.enchat-extensions")

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
        return loaded if isinstance(loaded, dict) else {}

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
            return json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc

    def get_manifest(self) -> IntegrationManifest:
        """Return manifest metadata for secure communications discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "enchat (extensions)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/sudodevdante/enchat"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Ephemeral encrypted terminal chat wrapper with blind-relay status reporting."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["ephemeral_encrypted_chat", "blind_relay_pathing", "secure_session_status"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local enchat runtime availability without external network calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_bin = self._env(f"{env_prefix}_BIN")
        if configured_bin and shutil.which(configured_bin):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute secure comms operation or return deterministic airgapped fixture."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or self._DEFAULT_OPERATION).strip().lower()
        if re.fullmatch(r"[a-z0-9_-]{1,64}", operation) is None:
            raise ValueError("operation must match ^[a-z0-9_-]{1,64}$")

        session_id = safe_params.get("session_id")
        if session_id is not None and re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", str(session_id)) is None:
            raise ValueError("session_id must match ^[A-Za-z0-9._:-]{1,128}$")

        message = safe_params.get("message")
        if message is not None:
            if not isinstance(message, str):
                raise ValueError("message must be a string")
            if len(message.encode("utf-8")) > 2048:
                raise ValueError("message must be <= 2048 bytes")

        relay_hops = safe_params.get("relay_hops")
        if relay_hops is not None:
            if not isinstance(relay_hops, int) or relay_hops < 0 or relay_hops > 7:
                raise ValueError("relay_hops must be an integer between 0 and 7")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning enchat fixture payload.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "status": "ok",
                "operation": operation,
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "request": safe_params,
                "message": "enchat runtime dependencies are not installed or configured.",
            }

        # Tactical note: runtime execution is orchestrator-owned to preserve OPSEC controls.
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": safe_params,
            "message": "Local enchat runtime detected; execution is delegated to mission orchestrator.",
        }
