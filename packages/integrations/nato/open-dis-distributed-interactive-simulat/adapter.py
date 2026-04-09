"""Adapter for Open-DIS distributed simulation interoperability.

Military/tactical context:
This wrapper supports deterministic C4I simulation interoperability checks used
for coalition rehearsal and command-post integration drills.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class OpenDisdistributedInteractiveAdapter(IntegrationAdapter):
    """S3M NATO adapter for Open-DIS interoperability validation workflows."""

    integration_id = "open-dis-distributed-interactive-simulat"
    domain = "nato"
    _COMMAND_CANDIDATES = ("python3", "pip3", "git")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        # Tactical requirement: fixed logger namespace for coalition replay analysis.
        self.logger = logging.getLogger("s3m.integrations.nato.open-dis-distributed-interactive-simulat")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest_dict(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            self.logger.warning("Manifest file missing: %s", manifest_path)
            return {}
        try:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
            return {}
        if not isinstance(data, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return data

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate untrusted payloads prior to simulation interoperability checks."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        if len(params) > 128:
            raise ValueError("params contains too many top-level fields")
        payload = json.loads(json.dumps(params))
        if len(json.dumps(payload)) > 20000:
            raise ValueError("params payload is too large")
        return payload

    def get_manifest(self) -> IntegrationManifest:
        """Return local manifest metadata for NATO simulation interoperability workflows."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Open-DIS (Distributed Interactive Simulation)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/open-dis"),
            license=str(raw.get("license") or "BSD-3-Clause"),
            description=str(
                raw.get("description")
                or "Distributed Interactive Simulation interoperability support for coalition C4I exercises."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["dis_interoperability", "c4i_simulation_exchange", "synthetic_battlefield_rehearsal"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local runtime prerequisites for Open-DIS integration tasks."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_").replace(".", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Wrap interoperability checks with deterministic fixture fallback."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or "validate_pdu_schema").strip().lower()
        if not operation or len(operation) > 64:
            raise ValueError("operation must be a non-empty string with at most 64 characters")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning Open-DIS fixture for interoperability drill.")
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
                "error": "open-dis runtime prerequisites are not installed or configured",
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local-runtime",
            "status": "ready",
            "operation": operation,
            "request": request,
            "note": "Local Open-DIS prerequisites validated; live network simulation remains mission-controlled.",
        }
