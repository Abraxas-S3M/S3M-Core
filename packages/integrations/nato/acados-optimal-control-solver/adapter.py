"""Adapter for ACADOS optimal-control solver workflows.

Military/tactical context:
This wrapper enables deterministic trajectory-optimization rehearsal for ISR
and swarm maneuver planning in denied, sovereign compute environments.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AcadosoptimalControlSolverAdapter(IntegrationAdapter):
    """S3M integration adapter for ACADOS mission-control optimization."""

    integration_id = "acados-optimal-control-solver"
    domain = "nato"
    _SUPPORTED_OPERATIONS = {"trajectory_optimization", "mpc_validation", "solver_benchmark"}
    _MODULE_CANDIDATES = ("acados_template", "acados")
    _COMMAND_CANDIDATES = ("acados", "acados_ocp_solver")

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

        if not isinstance(loaded, dict):
            self.logger.warning("Manifest is not a mapping: %s", manifest_path)
            return {}
        return loaded

    def get_manifest(self) -> IntegrationManifest:
        """Return adapter metadata for control and autonomy orchestration."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "ACADOS (optimal control solver)")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "BSD")),
            description=(
                "Optimal-control wrapper for constrained mission trajectory planning, "
                "model-predictive control rehearsal, and sovereign offline validation."
            ),
            integration_type="adapter",
            capabilities=["trajectory-optimization", "mpc", "solver-benchmarking"],
            airgapped_support=True,
        )

    def validate_availability(self) -> bool:
        """Validate local ACADOS runtime presence without external calls."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        module_available = any(importlib.util.find_spec(module_name) is not None for module_name in self._MODULE_CANDIDATES)
        command_available = any(shutil.which(command) is not None for command in self._COMMAND_CANDIDATES)
        return module_available or command_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute optimization wrapper flow with deterministic offline fallback."""
        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a dictionary when provided")

        request = params or {}
        operation = str(request.get("operation", "trajectory_optimization")).strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning ACADOS fixture for control rehearsal.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "status": "ok",
                "operation": operation,
                "request": request,
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
                "request": request,
                "message": "ACADOS tooling is not installed on this host.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": request,
            "message": "ACADOS availability checks passed; live solve execution is orchestrator-controlled.",
        }
