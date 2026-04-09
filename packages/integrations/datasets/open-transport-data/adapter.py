"""Adapter for Open Transport Data logistics-network datasets.

Military/tactical context:
This wrapper provides sovereign access to route and network topologies used for
mobility planning, sustainment simulation, and convoy route stress-testing in
airgapped command and training environments.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class OpenTransportDataAdapter(IntegrationAdapter):
    """Sovereign wrapper for transport-network datasets used in mission logistics."""

    integration_id = "open-transport-data"
    domain = "datasets"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _load_manifest(self) -> dict[str, Any]:
        raw_manifest = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw_manifest, dict):
            raise ValueError("Open Transport Data manifest must be a YAML mapping.")
        return raw_manifest

    def get_manifest(self) -> IntegrationManifest:
        """Load transport metadata required for tactical simulation registries."""
        raw = self._load_manifest()
        return IntegrationManifest(
            name=str(raw.get("name") or "Open Transport Data"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or "https://github.com/ITSLeeds/opentransportdata"),
            license=str(raw.get("license") or "Various"),
            description=str(
                raw.get("description")
                or "Transport network and route dataset adapter for logistics rehearsal and route analysis."
            ),
            integration_type=str(raw.get("integration_type") or "dataset"),
            capabilities=[str(item) for item in raw.get("capabilities", ["route_graphing", "logistics_simulation"])],
            pip_dependencies=[str(item) for item in raw.get("pip_dependencies", [])],
            system_dependencies=[str(item) for item in raw.get("system_dependencies", [])],
            docker_dependencies=[str(item) for item in raw.get("docker_dependencies", [])],
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def _dataset_path_candidates(self) -> list[Path]:
        """Resolve local mirrors that hold transport topology files."""
        candidates: list[Path] = []
        for key in ("OPEN_TRANSPORT_DATA_PATH", "S3M_TRANSPORT_DATA_PATH"):
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
        """Check local graph-processing tools and transport dataset mirrors."""
        if self.is_airgapped:
            fixture = self._read_fixture("sample_response.json")
            return isinstance(fixture, dict) and bool(fixture)

        path_available = any(path.exists() for path in self._dataset_path_candidates())
        tool_available = bool(shutil.which("python3") or shutil.which("python")) and (
            importlib.util.find_spec("pandas") is not None or importlib.util.find_spec("networkx") is not None
        )
        return path_available or tool_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run logistics-dataset workflow or airgapped fixture response."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("OpenTransportDataAdapter execute params must be a dictionary.")

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
                "detail": "Transport dataset mirror or graph tooling is unavailable on this node.",
            }

        action = str(request.get("action") or "load_transport_routes")
        return {
            "status": "accepted",
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": "online",
            "action": action,
            "request": request,
            "detail": "Dataset wrapper is ready for local orchestrator handoff without external API calls.",
        }
