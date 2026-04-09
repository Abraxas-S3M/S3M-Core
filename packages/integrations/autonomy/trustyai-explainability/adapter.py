"""trustyai-explainability integration adapter.

Military/tactical context:
This adapter provides local checks for JVM-based explainability and fairness
tooling, supporting mission AI accountability in disconnected deployments.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class TrustyaiExplainabilityAdapter(IntegrationAdapter):
    """Wrap TrustyAI explainability checks and execution responses."""

    integration_id = "trustyai-explainability"
    domain = "autonomy"

    def __init__(self, mode: str | None = None):
        super().__init__(mode=mode)
        self.logger = logging.getLogger("s3m.integrations.autonomy.trustyai-explainability")
        self._manifest_path = Path(__file__).resolve().parent / "manifest.yaml"

    @staticmethod
    def _coerce_list(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def get_manifest(self) -> IntegrationManifest:
        raw: dict[str, Any] = {}
        if self._manifest_path.exists():
            raw = yaml.safe_load(self._manifest_path.read_text(encoding="utf-8")) or {}

        return IntegrationManifest(
            name=str(raw.get("name") or "trustyai-explainability"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "Apache 2.0"),
            description=str(
                raw.get("description")
                or "JVM explainability and fairness metrics for tactical mission-model accountability."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["fairness_metrics", "explainability_algorithms", "jvm_xai_runtime"]
            ),
            system_dependencies=self._coerce_list(raw.get("system_dependencies") or ["java"]),
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        java_bin = shutil.which("java")
        trustyai_bin = shutil.which("trustyai")
        trustyai_jar = self._env("TRUSTYAI_JAR", "")
        jar_exists = bool(trustyai_jar) and Path(trustyai_jar).exists()
        return bool(java_bin) and bool(trustyai_bin or jar_exists)

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request = params or {}
        if self.is_airgapped:
            payload = self._read_fixture("sample_response.json")
            payload["execution_mode"] = "airgapped"
            payload["requested_action"] = str(request.get("action", "explain_prediction"))
            return payload

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "detail": "TrustyAI runtime not found (requires java and trustyai binary or TRUSTYAI_JAR).",
                "fallback": self._read_fixture("sample_response.json"),
            }

        java_version = ""
        java_bin = shutil.which("java")
        if java_bin:
            try:
                probe = subprocess.run(
                    [java_bin, "-version"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=8,
                )
                stream = probe.stderr.strip() or probe.stdout.strip()
                java_version = stream.splitlines()[0] if stream else ""
            except (subprocess.SubprocessError, OSError):
                java_version = ""

        return {
            "status": "ok",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "requested_action": str(request.get("action", "explain_prediction")),
            "java_version": java_version,
            "trustyai_jar": os.getenv("TRUSTYAI_JAR", ""),
            "tactical_note": "TrustyAI runtime is ready for fairness and explainability mission audits.",
        }
