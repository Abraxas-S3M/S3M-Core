"""Adapter for frappe/hrms personnel readiness workflows.

Military/tactical context:
This wrapper supports sovereign force-readiness tracking by exposing
deterministic personnel, attendance, and training status data in
disconnected command environments.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class HrmsAdapter(IntegrationAdapter):
    """S3M readiness adapter for frappe/hrms personnel systems."""

    integration_id = "hrms"
    domain = "readiness"
    _COMMAND_CANDIDATES = ("bench", "frappe-bench", "hrms")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            return {}
        loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}

    @staticmethod
    def _coerce_str_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate mission HR payloads before readiness orchestration."""
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
        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "hrms"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/frappe/hrms"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Open-source HR and payroll platform for personnel, attendance, and training administration."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["personnel_roster", "attendance_snapshot", "training_status"]
            ),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_str_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check whether local HRMS tooling is available on this node."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_path = self._env("HRMS_PATH").strip()
        if configured_path:
            return Path(configured_path).expanduser().exists()

        return any(shutil.which(command) is not None for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run readiness data access with deterministic fixture replay offline."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "personnel_roster").strip().lower()

        if self.is_airgapped:
            self.logger.info("Returning fixture output for readiness operation=%s", operation)
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
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "request": safe_params,
                "message": "HRMS runtime is not installed on this sovereign node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "HRMS adapter is available for local readiness orchestration.",
        }
