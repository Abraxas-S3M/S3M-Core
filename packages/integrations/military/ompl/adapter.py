"""Adapter for the Open Motion Planning Library (OMPL).

Military/tactical context:
This wrapper supports deterministic path-planning rehearsal for autonomous UAV
missions where route quality and obstacle avoidance must be validated on
sovereign infrastructure without external network dependencies.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class OmplAdapter(IntegrationAdapter):
    """S3M integration adapter for OMPL tactical path-planning workflows."""

    integration_id = "ompl"
    domain = "military"
    _COMMAND_CANDIDATES = ("ompl_benchmark", "ompl_app", "python3")

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.military.ompl")

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

    def _sanitize_params(self, params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate untrusted mission parameters before planner invocation."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        payload = json.loads(json.dumps(params))
        if len(json.dumps(payload)) > 20000:
            raise ValueError("params payload is too large")
        return payload

    def get_manifest(self) -> IntegrationManifest:
        """Return wrapper metadata for orchestrator capability discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "ompl")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "https://github.com/ompl/ompl")),
            license=str(raw.get("license", "BSD")),
            description=str(
                raw.get(
                    "description",
                    "Open Motion Planning Library for RRT* and related trajectory planning.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(
                raw.get(
                    "capabilities",
                    ["uav-path-planning", "rrt-star", "obstacle-aware-routing"],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local OMPL runtime prerequisites without network calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run OMPL wrapper logic with deterministic airgapped fallback."""
        try:
            request_params = self._sanitize_params(params)
        except ValueError as exc:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": str(exc),
            }

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning OMPL fixture for mission route rehearsal.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "request": request_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "OMPL toolchain is not installed or configured",
                "request": request_params,
            }

        operation = str(request_params.get("operation", "plan_path"))
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request_params,
            "note": "Local OMPL checks passed; live planner execution is delegated to mission autonomy nodes.",
        }
