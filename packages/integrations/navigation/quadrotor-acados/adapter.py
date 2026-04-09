"""Adapter for quadrotor_acados trajectory and formation control workflows.

Military/tactical context:
This wrapper standardizes formation-flight MPC checks for cooperative UAV teams
tasked with surveillance and route security in disconnected mission spaces.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class QuadrotorAcadosAdapter(IntegrationAdapter):
    """S3M adapter for quadrotor_acados navigation/control integration workflows."""

    integration_id = "quadrotor-acados"
    domain = "navigation"
    _COMMAND_CANDIDATES = ("python3", "cmake", "make")
    _ENV_PATH_KEYS = ("QUADROTOR_ACADOS_PATH", "ACADOS_SOURCE_DIR")
    _MODULE_CANDIDATES = ("acados_template", "casadi")
    _DEFAULT_OPERATION = "solve_formation_mpc"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger(f"s3m.integrations.navigation.{self.integration_id}")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

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

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate requests before tactical UAV formation-control processing."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc
        if len(json.dumps(normalized)) > 25000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Load quadrotor_acados metadata for navigation orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name") or "quadrotor_acados"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url") or "https://github.com/duynamrcv/quadrotor_acados"
            ),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "MPC for quadrotor trajectory and formation tracking using acados."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=list(
                raw.get(
                    "capabilities",
                    ["formation_mpc", "trajectory_tracking", "quadrotor_team_control"],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Validate local quadrotor_acados artifacts without external APIs."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured = [self._env(key) for key in self._ENV_PATH_KEYS]
        if any(value and Path(value).expanduser().exists() for value in configured):
            return True

        if any(importlib.util.find_spec(module) is not None for module in self._MODULE_CANDIDATES):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute quadrotor_acados wrapper behavior with fixture fallback."""
        try:
            safe_params = self._sanitize_params(params)
        except ValueError as exc:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": str(exc),
            }

        operation = str(safe_params.get("operation") or self._DEFAULT_OPERATION)
        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning quadrotor_acados fixture payload.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "request": safe_params,
                "result": self._read_fixture("sample_response.json"),
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "operation": operation,
                "request": safe_params,
                "message": "quadrotor_acados runtime is not installed or configured locally.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "quadrotor_acados dependencies validated; orchestrator may run formation-control flow.",
        }
