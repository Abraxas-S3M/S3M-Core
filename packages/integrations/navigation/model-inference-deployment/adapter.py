"""Adapter for the Model-Inference-Deployment framework index.

Military/tactical context:
This wrapper standardizes offline validation of inference-runtime options
required to deploy navigation and control models on disconnected edge nodes.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class ModelInferenceDeploymentAdapter(IntegrationAdapter):
    """S3M adapter for model-inference-deployment runtime selection workflows."""

    integration_id = "model-inference-deployment"
    domain = "navigation"

    _COMMAND_CANDIDATES = (
        "trtexec",
        "onnxruntime_perf_test",
        "tvmc",
        "benchmark_app",
        "python3",
    )
    _PYTHON_MODULE_CANDIDATES = (
        "onnxruntime",
        "tvm",
        "openvino",
        "tensorrt",
    )

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
        """Return integration metadata for mission planner discovery."""
        raw = self._load_manifest_dict()
        return IntegrationManifest(
            name=str(raw.get("name", "Model-Inference-Deployment")),
            slug=str(raw.get("slug", self.integration_id)),
            domain=str(raw.get("domain", self.domain)),
            source_url=str(raw.get("source_url", "")),
            license=str(raw.get("license", "Unknown")),
            description=str(
                raw.get(
                    "description",
                    "Curated matrix of TensorRT, ONNX Runtime, TVM, and OpenVINO deployment paths.",
                )
            ),
            integration_type=str(raw.get("integration_type", "adapter")),
            capabilities=list(
                raw.get(
                    "capabilities",
                    [
                        "runtime-selection",
                        "edge-inference-deployment",
                        "offline-readiness-checks",
                    ],
                )
            ),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Check local runtime tooling for airgapped mission deployment."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        env_prefix = self.integration_id.upper().replace("-", "_")
        configured_path = self._env(f"{env_prefix}_PATH")
        if configured_path and Path(configured_path).exists():
            return True

        configured_binary = self._env(f"{env_prefix}_BIN")
        if configured_binary and shutil.which(configured_binary):
            return True

        modules_ready = any(importlib.util.find_spec(module_name) for module_name in self._PYTHON_MODULE_CANDIDATES)
        commands_ready = any(shutil.which(command) for command in self._COMMAND_CANDIDATES)
        return modules_ready or commands_ready

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute runtime-selection wrapper with deterministic fixture fallback."""
        if params is not None and not isinstance(params, dict):
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "error",
                "error": "params must be a dictionary",
            }

        request = params or {}
        operation = str(request.get("operation", "framework_matrix"))

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; serving fixture data for %s.", self.integration_id)
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "result": self._read_fixture("sample_response.json"),
                "request": request,
            }

        if not self.validate_availability():
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "status": "unavailable",
                "error": "No supported inference runtime toolchain detected",
                "operation": operation,
                "request": request,
            }

        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "status": "ready",
            "operation": operation,
            "request": request,
            "note": "Local runtime checks passed; deployment execution remains under mission policy controls.",
        }
