"""Adapter for OpenC2SIM.github.io C2SIM standards resources.

Military/tactical context:
This wrapper exposes doctrine and schema reference access for command-and-
control simulation interoperability rehearsals in disconnected mission networks.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class Openc2simgithubioAdapter(IntegrationAdapter):
    """S3M integration adapter for OpenC2SIM.github.io reference materials."""

    integration_id = "openc2sim.github.io"
    domain = "interop"
    _COMMAND_CANDIDATES = ("jekyll", "bundle", "mkdocs")

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

    def get_manifest(self) -> IntegrationManifest:
        """Return metadata for tactical interop standards discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "OpenC2SIM.github.io")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "Official C2SIM standards and reference artifacts for simulation interoperation.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(
                raw.get("capabilities", ["c2sim_reference", "schema_guidance", "interop_doctrine"])
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local availability of C2SIM reference tooling or mirrored content."""
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
        """Provide C2SIM reference outputs with deterministic airgapped fallback."""
        if params is not None and not isinstance(params, dict):
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": "params must be a dictionary",
            }

        request_params = params or {}
        if self.is_airgapped:
            self.logger.info("Airgapped mode active; serving fixture for standards rehearsal.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "result": self._read_fixture("sample_response.json"),
                "request": request_params,
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "OpenC2SIM reference tooling is not installed or configured",
                "request": request_params,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": str(request_params.get("operation", "load_reference_bundle")),
            "request": request_params,
            "note": "Local OpenC2SIM references are reachable; mission orchestration controls live usage.",
        }
