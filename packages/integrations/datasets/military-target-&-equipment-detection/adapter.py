"""Adapter for Military Target & Equipment Detection training data.

Military/tactical context:
This wrapper lets commanders and autonomy developers stage equipment-recognition
rehearsals (rifles, tanks, aircraft, and dismounted personnel) without relying on
external network access in contested environments.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class MilitaryTargetEquipmentAdapter(IntegrationAdapter):
    """Sovereign integration wrapper for the military object-detection dataset."""

    integration_id = "military-target-&-equipment-detection"
    domain = "datasets"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("Military Target & Equipment Detection manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load metadata required by tactical catalog discovery and planning."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "Military Target & Equipment Detection"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/KarthikPrabhu2541/Military-Target-and-Equipment-Detection"
            ),
            license=str(raw.get("license") or "MIT (repo); dataset "),
            description=str(
                raw.get("description")
                or "YOLO-oriented military equipment image dataset adapter for edge mission rehearsal."
            ),
            integration_type=str(raw.get("integration_type") or "dataset"),
            capabilities=[str(item) for item in raw.get("capabilities", ["object_detection", "equipment_classification"])],
            pip_dependencies=[str(item) for item in raw.get("pip_dependencies", [])],
            system_dependencies=[str(item) for item in raw.get("system_dependencies", [])],
            docker_dependencies=[str(item) for item in raw.get("docker_dependencies", [])],
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def _dataset_path_candidates(self) -> list[Path]:
        """Return local dataset checkpoints that can be used in sovereign deployments."""
        candidates: list[Path] = []
        for key in ("MILITARY_TARGET_EQUIPMENT_DATASET_PATH", "S3M_MIL_TARGET_EQUIP_PATH"):
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
        """Check local detector tooling and mirrored data availability."""
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            return isinstance(fixture, dict) and bool(fixture)

        path_available = any(path.exists() for path in self._dataset_path_candidates())
        tool_available = bool(shutil.which("yolo")) or importlib.util.find_spec("ultralytics") is not None
        return path_available or tool_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run dataset access workflow, or deterministic fixture fallback when offline."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("MilitaryTargetEquipmentAdapter execute params must be a dictionary.")

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
                "detail": "YOLO runtime or mirrored dataset path is not available on this node.",
            }

        action = str(request.get("action") or "load_detection_dataset")
        return {
            "status": "accepted",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": "online",
            "action": action,
            "request": request,
            "detail": "Dataset wrapper is ready for local orchestrator handoff without external API calls.",
        }
