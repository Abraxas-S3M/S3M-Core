"""Adapter for NVIDIA TensorRT-Edge-LLM runtime.

Military/tactical context:
This wrapper verifies local high-throughput LLM/VLM runtime readiness for
navigation command-assist tasks on Jetson platforms in denied networks.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class TensorrtEdgeLlmAdapter(IntegrationAdapter):
    """S3M integration adapter for TensorRT-Edge-LLM."""

    integration_id = "tensorrt-edge-llm"
    domain = "navigation"
    _COMMAND_CANDIDATES = ("trtllm-build", "trtllm-serve", "trtexec")
    _PYTHON_MODULE_CANDIDATES = ("tensorrt", "tensorrt_llm")

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

    def get_manifest(self) -> IntegrationManifest:
        """Return runtime metadata for tactical orchestration lookup."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "TensorRT-Edge-LLM")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "High-performance C++ inference runtime for LLMs/VLMs on Jetson and embedded systems.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(
                raw.get(
                    "capabilities",
                    ["llm-inference", "vlm-inference", "jetson-optimization"],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local TensorRT-Edge-LLM tool availability offline."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        if any(importlib.util.find_spec(module_name) for module_name in self._PYTHON_MODULE_CANDIDATES):
            return True

        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute edge-LLM wrapper with fixture fallback for offline drills."""
        if params is not None and not isinstance(params, dict):
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": "params must be a dictionary",
            }

        request_params = params or {}
        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning TensorRT-Edge-LLM fixture.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "result": self._read_fixture("sample_response.json"),
                "request": request_params,
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "tensorrt-edge-llm is not installed or configured",
                "request": request_params,
            }

        operation = str(request_params.get("operation", "edge_llm_inference"))
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request_params,
            "note": "Local TensorRT-Edge-LLM checks passed; live model serving remains mission-governed.",
        }
