"""Adapter for OSINT-BIBLE.

Military/tactical context:
This wrapper provides a stable interface to OSINT doctrine references so
analysts can assemble methodical briefing pipelines in disconnected theaters.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class OsintBibleAdapter(IntegrationAdapter):
    """S3M adapter for OSINT-BIBLE methodology and resource indexing."""

    integration_id = "osint-bible"
    domain = "intel"
    _REPO_ENV_VAR = "OSINT_BIBLE_PATH"
    _COMMAND_CANDIDATES = ("git",)

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate payload shape and size for secure mission compute nodes."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if len(params) > 128:
            raise ValueError("params contains too many top-level fields")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc
        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large")
        return normalized

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
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return loaded

    def get_manifest(self) -> IntegrationManifest:
        """Return parsed manifest for integration registry and orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "OSINT-BIBLE")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/frangelbarrera/OSINT-BIBLE")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "Comprehensive guide to OSINT tools, methodologies, and mission support resources.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=self._coerce_list(
                raw.get("capabilities", ["methodology_guidance", "resource_cataloging", "briefing_support"])
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path", "")),
        )

    def validate_availability(self) -> bool:
        """Check local availability for sovereign intelligence preparation."""
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            return isinstance(fixture, dict) and bool(fixture)

        configured_path = self._env(self._REPO_ENV_VAR)
        if configured_path:
            candidate = Path(configured_path).expanduser()
            if candidate.exists() and (candidate / "README.md").exists():
                return True

        local_mirror = Path(f"/opt/s3m/integrations/intel/{self.integration_id}")
        if local_mirror.exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute methodology lookup workflow with deterministic fixture fallback."""
        request = self._sanitize_params(params)
        if self.is_airgapped:
            self.logger.info("Airgapped mode enabled; returning OSINT-BIBLE fixture payload.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "local-wrapper",
                "status": "unavailable",
                "error": "OSINT-BIBLE local mirror is not configured",
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local-wrapper",
            "status": "ready",
            "operation": str(request.get("operation", "doctrine_lookup")),
            "request": request,
            "note": "OSINT-BIBLE methodology references are available for intelligence planning.",
        }
