"""Adapter for Clermont command-center readiness dashboard workflows.

Military/tactical context:
This wrapper provides deterministic readiness visualization snapshots for
multi-view command-center planning in degraded or disconnected environments.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
import re
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class ClermontAdapter(IntegrationAdapter):
    """S3M integration adapter for the Clermont dashboard toolkit."""

    integration_id = "clermont"
    domain = "readiness"
    _COMMAND_CANDIDATES = ("clermont", "npm", "node")
    _MODULE_CANDIDATES = ("clermont",)

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        # Tactical requirement: fixed logger name for after-action trace correlation.
        self.logger = logging.getLogger("s3m.integrations.readiness.clermont")

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
        """Return metadata required by readiness orchestration layers."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "Clermont"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/SageHourihan/clermont"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Cold-war style command center dashboard for multi-view operational monitoring."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities") or ["multi_view_dashboard", "operational_timeline", "status_wallboard"]
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local runtime availability without reaching external services."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_").replace(".", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        if any(importlib.util.find_spec(module_name) for module_name in self._MODULE_CANDIDATES):
            return True
        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute dashboard wrapper request with deterministic airgapped fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise TypeError("params must be a dictionary")

        view = str(request.get("view", "command_overview")).strip().lower()
        if not view or len(view) > 64 or re.fullmatch(r"[a-z0-9_-]+", view) is None:
            raise ValueError("view must match ^[a-z0-9_-]{1,64}$")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning Clermont fixture payload.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "view": view,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "Clermont runtime is not installed or configured",
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local-runtime",
            "status": "ready",
            "view": view,
            "request": request,
            "result": {
                "status": "ready",
                "dashboard_state": "renderable",
            },
        }
