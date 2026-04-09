"""Adapter for VehicleDetection SAR small-object surveillance data.

Military/tactical context:
This wrapper enables SAR-based convoy and vehicle signature training for remote
area surveillance, helping ISR teams evaluate small-object detection pipelines in
denied communications environments.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class VehicledetectionsarSmallObjectAdapter(IntegrationAdapter):
    """Sovereign wrapper for SAR vehicle small-object detection datasets."""

    integration_id = "vehicledetection-sar-small-object"
    domain = "datasets"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("VehicleDetection manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load metadata used by tactical dataset discovery services."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "VehicleDetection (SAR Small Object)"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/KK-MUT/VehicleDetection"),
            license=str(raw.get("license") or "Request from authors"),
            description=str(
                raw.get("description")
                or "SAR radar image dataset adapter for small-object vehicle detection in surveillance missions."
            ),
            integration_type=str(raw.get("integration_type") or "dataset"),
            capabilities=[str(item) for item in raw.get("capabilities", ["sar_detection", "small_object_tracking"])],
            pip_dependencies=[str(item) for item in raw.get("pip_dependencies", [])],
            system_dependencies=[str(item) for item in raw.get("system_dependencies", [])],
            docker_dependencies=[str(item) for item in raw.get("docker_dependencies", [])],
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def _dataset_path_candidates(self) -> list[Path]:
        """Resolve possible sovereign mirrors of the SAR dataset."""
        candidates: list[Path] = []
        for key in ("VEHICLEDETECTION_DATASET_PATH", "S3M_SAR_VEHICLE_DATASET_PATH"):
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
        """Check local SAR dataset mirrors and utility tools for execution readiness."""
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            return isinstance(fixture, dict) and bool(fixture)

        path_available = any(path.exists() for path in self._dataset_path_candidates())
        tool_available = bool(shutil.which("git")) and bool(shutil.which("python3") or shutil.which("python"))
        return path_available or tool_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run SAR dataset adapter workflow with deterministic offline fallback."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("VehicledetectionsarSmallObjectAdapter execute params must be a dictionary.")

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
                "detail": "SAR dataset mirror or local preprocessing toolchain is unavailable.",
            }

        action = str(request.get("action") or "prepare_sar_dataset")
        return {
            "status": "accepted",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": "online",
            "action": action,
            "request": request,
            "detail": "Dataset wrapper is prepared for local orchestrator handoff without external API calls.",
        }
