"""Adapter for ONNX Runtime to TensorRT optimization workflow.

Military/tactical context:
This wrapper supports validating optimized ONNX-to-TensorRT deployment paths
for navigation models on mission hardware with strict latency constraints.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class OnnxruntimeTensorrtAdapter(IntegrationAdapter):
    """S3M integration adapter for Onnxruntime-TensorRT."""

    integration_id = "onnxruntime-tensorrt"
    domain = "navigation"
    _COMMAND_CANDIDATES = ("trtexec", "onnxruntime_perf_test", "python3")
    _PYTHON_MODULE_CANDIDATES = ("onnxruntime", "tensorrt")

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
        """Return optimization adapter metadata for orchestrator consumption."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "Onnxruntime-TensorRT")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "ONNX to TensorRT optimization with FP16/INT8 quantization and multi-GPU workflows.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(
                raw.get(
                    "capabilities",
                    ["onnx-optimization", "fp16-int8-quantization", "tensorrt-deployment"],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Validate local optimization stack availability for secure offline missions."""
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
        """Execute optimization wrapper with deterministic airgapped replay."""
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
            self.logger.info("Airgapped mode active; returning Onnxruntime-TensorRT fixture.")
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
                "error": "onnxruntime-tensorrt is not installed or configured",
                "request": request_params,
            }

        operation = str(request_params.get("operation", "optimize_onnx_to_tensorrt"))
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request_params,
            "note": "Local optimization stack checks passed; live conversion remains mission-policy controlled.",
        }
