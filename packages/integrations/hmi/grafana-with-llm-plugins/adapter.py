"""Grafana with LLM plugins adapter for Human-Machine Teaming observability.

Military/tactical context:
This wrapper supports command-level telemetry and AI trace oversight using local
Grafana dashboards that remain operable in denied or disconnected environments.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class GrafanawithLlmPluginsAdapter(IntegrationAdapter):
    """Integration wrapper for Grafana observability with LLM plugin context."""

    integration_id = "grafana-with-llm-plugins"
    domain = "hmi"
    _SUPPORTED_OPERATIONS = {"dashboard_status", "otel_trace_rollup", "llm_panel_summary"}
    _MODULE_CANDIDATES = ("grafana_api",)
    _COMMAND_CANDIDATES = ("grafana-server", "grafana-cli")

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
        """Validate mission payloads before dashboard processing."""
        if params is None:
            return {}
        if not isinstance(params, dict):
            raise ValueError("params must be a dictionary")
        if any(not isinstance(key, str) for key in params):
            raise ValueError("params keys must be strings")
        if len(params) > 128:
            raise ValueError("params contains too many top-level fields")

        # Tactical safety: enforce JSON-safe payloads for deterministic operations.
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
            name=str(raw.get("name") or "Grafana (with LLM plugins)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/grafana/grafana"),
            license=str(raw.get("license") or "AGPL-3.0"),
            description=str(
                raw.get("description")
                or "Composable observability platform with AI/LLM tracing dashboards and OpenTelemetry integration."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["dashboard_observability", "otel_trace_analysis", "llm_plugin_monitoring"]
            ),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_str_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check if Grafana tooling is locally available."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        module_available = any(importlib.util.find_spec(module) is not None for module in self._MODULE_CANDIDATES)
        command_available = any(shutil.which(command) is not None for command in self._COMMAND_CANDIDATES)
        return module_available or command_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute observability workflow with deterministic airgapped fallback."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "dashboard_status").strip().lower()
        if operation not in self._SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation '{operation}' for {self.integration_id}")

        if self.is_airgapped:
            self.logger.info("Returning fixture output for tactical Grafana operation=%s", operation)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "request": safe_params,
                "data": self._read_fixture("sample_response.json"),
            }

        available = self.validate_availability()
        if not available:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "runtime",
                "status": "unavailable",
                "operation": operation,
                "request": safe_params,
                "message": "Grafana tooling is not installed on this sovereign node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "Grafana adapter is ready for local observability handoff.",
        }
