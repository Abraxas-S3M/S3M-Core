"""Adapter for SOC-Multitool extension ecosystems.

Military/tactical context:
The wrapper exposes extension-assisted investigative workflows as a stable
interface for SOC analysts operating under contested cyber conditions.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class SocMultitoolExtensionsAdapter(IntegrationAdapter):
    """Wrap SOC-Multitool extension functionality for S3M orchestration."""

    integration_id = "soc-multitool-extensions"
    domain = "cyber"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self._manifest_path = Path(__file__).resolve().parent / "manifest.yaml"

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata from local manifest YAML."""
        raw_manifest = yaml.safe_load(self._manifest_path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("SOC-Multitool extensions manifest must be a mapping.")

        return IntegrationManifest(
            name=str(raw_manifest.get("name") or "SOC-Multitool extensions"),
            slug=str(raw_manifest.get("slug") or self.integration_id),
            domain=str(raw_manifest.get("domain") or self.domain),
            source_url=str(raw_manifest.get("source_url") or ""),
            license=str(raw_manifest.get("license") or "Unknown"),
            description=str(
                raw_manifest.get("description")
                or "Browser extensions and tooling that streamline SOC investigations."
            ),
            integration_type=str(raw_manifest.get("integration_type") or "adapter"),
            capabilities=[str(item) for item in raw_manifest.get("capabilities", [])],
            pip_dependencies=[str(item) for item in raw_manifest.get("pip_dependencies", [])],
            system_dependencies=[str(item) for item in raw_manifest.get("system_dependencies", [])],
            docker_dependencies=[str(item) for item in raw_manifest.get("docker_dependencies", [])],
            airgapped_support=bool(raw_manifest.get("airgapped_support", True)),
            vendor_path=str(raw_manifest.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Check if extension resources or helper binaries exist locally."""
        fixture_path = self._fixture_dir / "sample_response.json"
        if self.is_airgapped:
            return fixture_path.exists()

        configured_path = Path(
            self._env("SOC_MULTITOOL_EXTENSIONS_PATH", str(Path.cwd() / "vendors" / self.integration_id))
        )
        known_binary = shutil.which("soc-multitool")
        return configured_path.exists() or known_binary is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute SOC multitool workflow wrappers with strict input checks."""
        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a dictionary when provided.")

        safe_params = params or {}
        workflow = str(safe_params.get("workflow", "investigation_assist"))
        case_id = str(safe_params.get("case_id", "UNSPECIFIED"))
        max_artifacts = int(safe_params.get("limit", 20))

        if max_artifacts < 1 or max_artifacts > 500:
            raise ValueError("limit must be between 1 and 500 for controlled SOC artifact output.")

        if self.is_airgapped:
            fixture_payload = self._read_fixture("sample_response.json")
            if not isinstance(fixture_payload, dict):
                raise ValueError("sample_response.json fixture must contain a JSON object.")

            artifacts = fixture_payload.get("artifacts", [])
            if isinstance(artifacts, list):
                fixture_payload["artifacts"] = artifacts[:max_artifacts]
            fixture_payload["mode"] = "airgapped"
            fixture_payload["workflow"] = workflow
            fixture_payload["case_id"] = case_id
            return fixture_payload

        if not self.validate_availability():
            raise RuntimeError(
                "SOC-Multitool extension resources are not available locally; "
                "set SOC_MULTITOOL_EXTENSIONS_PATH or enable airgapped mode."
            )

        # Tactical note: online mode remains local-only to preserve sovereign boundaries.
        return {
            "integration": self.integration_id,
            "mode": "online",
            "status": "available",
            "workflow": workflow,
            "case_id": case_id,
            "limit": max_artifacts,
            "data_source": "local_installation",
            "message": "Local SOC-Multitool extension resources are reachable for analyst workflows.",
        }

