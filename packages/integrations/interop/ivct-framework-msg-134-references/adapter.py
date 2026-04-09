"""Adapter for IVCT Framework references tied to MSG-134 interoperability.

Military/tactical context:
This wrapper exposes verification/certification references used to validate
HLA, DIS, and C2SIM interoperability before coalition mission execution.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class IvctFrameworkmsg134Adapter(IntegrationAdapter):
    """Expose IVCT/MSG-134 references with deterministic fixture handling."""

    integration_id = "ivct-framework-msg-134-references"
    domain = "interop"

    _REPO_ENV_VAR = "IVCT_FRAMEWORK_MSG_134_REFERENCES_PATH"
    _COMMAND_CANDIDATES = ("java", "mvn", "gradle")

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @staticmethod
    def _sanitize_params(params: dict[str, Any] | None) -> dict[str, Any]:
        """Validate operator test-run requests for secure V&V workflows."""
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

    def _load_manifest(self) -> dict[str, Any]:
        loaded = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}

    def get_manifest(self) -> IntegrationManifest:
        """Load IVCT metadata consumed by S3M interoperability orchestrators."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "IVCT_Framework (MSG-134 references)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "References in NATO MSG-134 GitHub org (historical)"),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Interoperability Verification and Certification Tool references for HLA/DIS/C2SIM."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["federation_verification", "hla_dis_c2sim_testing", "compliance_reference"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Validate local IVCT runtime/toolchain availability."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        configured_path = self._env(self._REPO_ENV_VAR)
        if configured_path and Path(configured_path).expanduser().exists():
            return True
        return any(shutil.which(command) for command in self._COMMAND_CANDIDATES)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Wrap interoperability verification calls for mission rehearsal."""
        request = self._sanitize_params(params)
        operation = str(request.get("operation") or "conformance_assessment")

        if self.is_airgapped:
            self.logger.info("Airgapped mode active; returning IVCT fixture response.")
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "operation": operation,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        available = self.validate_availability()
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local-wrapper",
            "operation": operation,
            "available": available,
            "status": "ready" if available else "unavailable",
            "request": request,
            "detail": (
                "IVCT verification toolchain is available for interoperability certification drills."
                if available
                else "Install Java build tooling or set IVCT_FRAMEWORK_MSG_134_REFERENCES_PATH."
            ),
        }
