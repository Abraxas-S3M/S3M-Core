"""Adapter for bitsandbytes quantization runtime.

Military/tactical context:
This wrapper confirms low-memory quantization tooling is mission-ready on
offline GPU systems, enabling larger sovereign models to run on constrained
edge hardware during contested operations.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class BitsandbytesAdapter(IntegrationAdapter):
    """S3M core tooling adapter for bitsandbytes quantization."""

    integration_id = "bitsandbytes"
    domain = "core_tooling"
    _COMMAND_CANDIDATES = ("bitsandbytes",)
    _PYTHON_MODULE_CANDIDATES = ("bitsandbytes",)

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _manifest_data(self) -> dict[str, Any]:
        manifest_path = self._manifest_path()
        if not manifest_path.exists():
            return {}
        try:
            loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            self.logger.exception("Failed to parse manifest YAML at %s", manifest_path)
            return {}
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
        """Validate quantization requests before local runtime dispatch."""
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
        """Return wrapper metadata used by tactical integration discovery."""
        raw = self._manifest_data()
        return IntegrationManifest(
            name=str(raw.get("name") or "BitsAndBytes"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/TimDettmers/bitsandbytes"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "4/8-bit quantization runtime for memory-efficient sovereign model deployment."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_str_list(
                raw.get("capabilities")
                or ["4bit-quantization", "8bit-quantization", "memory-optimization"]
            ),
            pip_dependencies=self._coerce_str_list(raw.get("pip_dependencies") or ["bitsandbytes"]),
            system_dependencies=self._coerce_str_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_str_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check if bitsandbytes runtime is installed on this sovereign node."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_path = self._env("BITSANDBYTES_PATH").strip()
        if configured_path and Path(configured_path).expanduser().exists():
            return True

        configured_bin = self._env("BITSANDBYTES_BIN").strip()
        if configured_bin and shutil.which(configured_bin):
            return True

        if any(importlib.util.find_spec(module_name) for module_name in self._PYTHON_MODULE_CANDIDATES):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute quantization wrapper with deterministic offline fixture replay."""
        safe_params = self._sanitize_params(params)
        operation = str(safe_params.get("operation") or "quantize_model").strip().lower()

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning bitsandbytes fixture for operation=%s", operation)
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
                "message": "bitsandbytes is not installed or configured on this node.",
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "runtime",
            "status": "ready",
            "operation": operation,
            "request": safe_params,
            "message": "bitsandbytes runtime checks passed for local quantization workflows.",
        }
