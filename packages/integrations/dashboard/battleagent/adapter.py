"""BattleAgent adapter for LLM-assisted battle emulation dashboards."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class BattleagentAdapter(IntegrationAdapter):
    """Wraps BattleAgent for tactical planning boards and multi-modal emulation output."""

    integration_id = "battleagent"
    domain = "dashboard"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("BattleAgent manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata for tactical orchestration discovery."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "BattleAgent"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/agiresearch/BattleAgent"),
            license=str(raw.get("license") or "Apache 2.0"),
            description=str(
                raw.get("description")
                or "LLM-based battle emulation with multi-modal tactical planning dashboard support."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=[str(item) for item in raw.get("capabilities") or ["llm_emulation", "course_of_action"]],
            airgapped_support=bool(raw.get("airgapped_support", True)),
        )

    def validate_availability(self) -> bool:
        """Confirm BattleAgent installation locally for disconnected deployments."""
        if self.is_airgapped:
            return bool(self._read_fixture("sample_response.json"))

        install_path = self._env("BATTLEAGENT_PATH").strip()
        if install_path:
            return Path(install_path).expanduser().exists()

        return any(shutil.which(command) for command in ("battleagent", "battle-agent"))

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute battle emulation retrieval, replaying fixture intelligence in airgapped mode."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("BattleAgent execute params must be a dictionary.")

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if not isinstance(fixture, dict) or not fixture:
                raise FileNotFoundError("Missing BattleAgent fixture: sample_response.json")
            response = dict(fixture)
            response["mode"] = "airgapped"
            response["request"] = request
            return response

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "detail": "BattleAgent CLI or local checkout path was not found.",
            }

        # Tactical control: wrapper intentionally avoids online model execution in this revision.
        return {
            "status": "deferred",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": "online",
            "request": request,
            "detail": "Local BattleAgent execution is available but intentionally stubbed.",
        }

