"""Adapter for Panopticon AI scenario datasets.

Military/tactical context:
This wrapper supplies scenario packs for reinforcement-learning and wargaming
experiments so planners can evaluate doctrine and agent behavior in sovereign,
offline simulation stacks.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class PanopticonAiScenariosAdapter(IntegrationAdapter):
    """Sovereign integration wrapper for Panopticon AI scenario datasets."""

    integration_id = "panopticon-ai-scenarios"
    domain = "datasets"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("Panopticon AI Scenarios manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load scenario metadata used by tactical training catalog services."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "Panopticon AI Scenarios"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/Panopticon-AI-team/panopticon"),
            license=str(raw.get("license") or "MIT"),
            description=str(
                raw.get("description")
                or "Wargaming scenario dataset adapter for RL/AI agent training in military modeling."
            ),
            integration_type=str(raw.get("integration_type") or "dataset"),
            capabilities=[str(item) for item in raw.get("capabilities", ["wargaming_scenarios", "rl_training"])],
            pip_dependencies=[str(item) for item in raw.get("pip_dependencies", [])],
            system_dependencies=[str(item) for item in raw.get("system_dependencies", [])],
            docker_dependencies=[str(item) for item in raw.get("docker_dependencies", [])],
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def _dataset_path_candidates(self) -> list[Path]:
        """Resolve local scenario-pack mirrors for sovereign deployments."""
        candidates: list[Path] = []
        for key in ("PANOPTICON_SCENARIO_PATH", "S3M_PANOPTICON_SCENARIO_PATH"):
            value = self._env(key).strip()
            if value:
                candidates.append(Path(value).expanduser())
        candidates.extend(
            [
                Path("/opt/s3m/datasets") / self.integration_id,
                Path("/data/s3m/datasets") / self.integration_id,
                Path.home() / "s3m-datasets" / self.integration_id,
            ]
        )
        return candidates

    def validate_availability(self) -> bool:
        """Check local scenario tooling and mirrored package availability."""
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            return isinstance(fixture, dict) and bool(fixture)

        path_available = any(path.exists() for path in self._dataset_path_candidates())
        tool_available = bool(shutil.which("python3") or shutil.which("python")) and (
            importlib.util.find_spec("gymnasium") is not None or shutil.which("panopticon") is not None
        )
        return path_available or tool_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run scenario-dataset workflow with deterministic offline fixture support."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("PanopticonAiScenariosAdapter execute params must be a dictionary.")

        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            if not isinstance(fixture, dict) or not fixture:
                raise FileNotFoundError("Missing fixture file: sample_response.json")
            return {
                "status": "ok",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": "airgapped",
                "source": "fixture",
                "request": request,
                "result": fixture,
            }

        if not self.validate_availability():
            return {
                "status": "unavailable",
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": "online",
                "request": request,
                "detail": "Panopticon scenario mirror or local simulation tooling is unavailable.",
            }

        action = str(request.get("action") or "load_wargaming_scenarios")
        return {
            "status": "accepted",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": "online",
            "action": action,
            "request": request,
            "detail": "Dataset wrapper is ready for local orchestrator handoff without external API calls.",
        }
