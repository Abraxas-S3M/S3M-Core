"""Adapter for ML-based vehicle predictive maintenance workflows.

Military/tactical context:
This wrapper supports motor-pool readiness by providing deterministic local
health predictions and alert summaries for ground platforms during disconnected
or contested operations.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class MlBasedVehiclePredictiveAdapter(IntegrationAdapter):
    """S3M integration wrapper for ML-based vehicle predictive maintenance."""

    integration_id = "ml-based-vehicle-predictive-maintenance-"
    domain = "maintenance"

    _SUPPORTED_OPERATIONS = {"health_prediction", "fault_alerts", "maintenance_priority"}
    _MODULE_CANDIDATES = ("lightgbm", "xgboost", "sklearn")
    _COMMAND_CANDIDATES = ("python3", "streamlit")
    _LOCAL_PATH_ENV = "ML_BASED_VEHICLE_PREDICTIVE_MAINTENANCE_PATH"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            return {}
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate vehicle-maintenance payloads before local processing."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        if len(params) > 128:
            raise ValueError("params contains too many top-level fields")

        try:
            normalized = json.loads(json.dumps(params))
        except (TypeError, ValueError) as exc:
            raise ValueError("params must be JSON-serializable") from exc

        if len(json.dumps(normalized)) > 20000:
            raise ValueError("params payload is too large")
        return normalized

    def get_manifest(self) -> IntegrationManifest:
        """Return manifest metadata for sovereign maintenance orchestration."""
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(
                raw.get("name")
                or "ML-Based-Vehicle-Predictive-Maintenance-System-with-Real-Time-Visualization"
            ),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/iDharshan/ML-Based-Vehicle-Predictive-Maintenance-System-with-Real-Time-Visualization"
            ),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "GBM-based vehicle predictive maintenance with real-time visualization workflows."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["vehicle-health-prediction", "fault-alerting", "maintenance-priority-ranking"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check whether local vehicle predictive tooling is reachable."""
        if self.is_airgapped:
            fixture_payload = self._read_fixture("sample_response.json")
            return isinstance(fixture_payload, dict) and bool(fixture_payload)

        configured_path = self._env(self._LOCAL_PATH_ENV)
        if configured_path:
            return Path(configured_path).expanduser().exists()

        module_available = any(importlib.util.find_spec(name) is not None for name in self._MODULE_CANDIDATES)
        command_available = any(shutil.which(command) is not None for command in self._COMMAND_CANDIDATES)
        return module_available or command_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute predictive requests with deterministic airgapped fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "health_prediction").strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning fixture output for tactical vehicle operation=%s", operation)
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
                "message": "Vehicle predictive maintenance tooling is not installed on this node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": safe_params,
            "message": "Vehicle predictive maintenance adapter is ready for local handoff.",
        }
