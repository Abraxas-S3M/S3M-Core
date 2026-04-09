"""Adapter for Metasploit exploitation validation workflows.

Military/tactical context:
This wrapper enables controlled exploitability validation against authorized
targets to measure mission-system resilience without exposing external services.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class MetasploitAdapter(IntegrationAdapter):
    """S3M integration adapter for Metasploit validation routines."""

    integration_id = "metasploit"
    domain = "military"
    _COMMAND_CANDIDATES = ("msfconsole", "msfvenom", "msfrpcd")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate operation payload before tactical execution routing."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if len(params) > 64:
            raise ValueError("params contains too many top-level fields")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")

        # Tactical safety: normalize to JSON-safe payloads before processing.
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc

        if len(json.dumps(normalized)) > 10000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Return integration metadata for military orchestration discovery."""
        manifest_path = self._manifest_path()
        raw: dict[str, Any] = {}
        if manifest_path.exists():
            try:
                loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                self.logger.exception("Manifest YAML parsing failed: %s", manifest_path)
                loaded = {}
            if isinstance(loaded, dict):
                raw = loaded

        return IntegrationManifest(
            name=str(raw.get("name") or "Metasploit"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/rapid7/metasploit-framework"),
            license=str(raw.get("license") or "BSD-3-Clause"),
            description=str(
                raw.get("description")
                or "Exploitation and validation framework for controlled red-team mission exercises."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["exploit_validation", "payload_simulation", "attack_surface_testing"]
            ),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_str_list(
                raw.get("system_dependencies") or ["msfconsole", "msfrpcd"]
            ),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local Metasploit availability with no remote dependency checks."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_binary = self._env("METASPLOIT_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env("METASPLOIT_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute Metasploit wrapper flow with deterministic fixture fallback."""
        safe_params = self._sanitize_params(params)

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "live",
                "status": "unavailable",
                "error": "metasploit is not installed or configured",
                "request": safe_params,
            }

        operation = str(safe_params.get("operation", "validate_exploit_path"))
        target = str(safe_params.get("target", "unspecified-target"))
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "live",
            "status": "ready",
            "operation": operation,
            "target": target,
            "request": safe_params,
            "note": "Metasploit tooling detected locally; authorize live actions through mission rules of engagement.",
        }
