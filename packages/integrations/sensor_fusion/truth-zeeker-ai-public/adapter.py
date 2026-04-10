"""Adapter for Truth-Zeeker Zeek-log anomaly detection pipelines.

Military/tactical context:
This wrapper supports cyber-intelligence fusion by providing deterministic,
airgapped-safe triage outputs from Zeek telemetry in defended enclaves.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class TruthZeekerAiPublicAdapter(IntegrationAdapter):
    """S3M wrapper for Truth-Zeeker-AI-Public workflows."""

    integration_id = "truth-zeeker-ai-public"
    domain = "sensor_fusion"

    _SUPPORTED_OPERATIONS = {"zeek_parse", "anomaly_score", "alert_summary"}
    _MODULE_CANDIDATES = ("pandas", "numpy")
    _COMMAND_CANDIDATES = ("zeek", "python3")
    _DEFAULT_OPERATION = "anomaly_score"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.sensor_fusion.truth-zeeker-ai-public")

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
        """Validate mission payloads before Zeek-log fusion analysis."""
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
        """Return integration metadata for sovereign sensor-fusion orchestration."""
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "Truth-Zeeker-AI-Public"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/dr-rakshith-truth-zeeker/Truth-Zeeker-AI-Public"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "AI-driven Zeek log parser and anomaly detection workflow for cyber sensor fusion."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities") or ["zeek_log_parsing", "session_anomaly_detection", "threat_signal_correlation"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check local runtime readiness without external network dependency."""
        if self.is_airgapped:
            fixture_payload = self._read_fixture("sample_response.json")
            return isinstance(fixture_payload, dict) and bool(fixture_payload)

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_bin = self._env(f"{env_prefix}_BIN")
        if configured_bin and shutil.which(configured_bin):
            return True

        module_available = any(importlib.util.find_spec(name) is not None for name in self._MODULE_CANDIDATES)
        command_available = any(shutil.which(command) is not None for command in self._COMMAND_CANDIDATES)
        return module_available or command_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute wrapper flow with deterministic fixture output in airgapped mode."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or self._DEFAULT_OPERATION).strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning fixture payload for tactical operation=%s", operation)
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
                "message": "Required local Zeek-anomaly dependencies are unavailable.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "accepted",
            "operation": operation,
            "request": safe_params,
            "message": "Local readiness checks passed; execution remains orchestrator-governed.",
        }
