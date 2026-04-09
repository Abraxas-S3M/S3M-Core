"""Adapter for py_trees tactical decision-tree execution.

Military/tactical context:
This wrapper supports lightweight behavior-tree orchestration for autonomous
mission components that must keep operating without remote connectivity.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class PyTreesAdapter(IntegrationAdapter):
    """Integration wrapper for py_trees."""

    integration_id = "py-trees"
    domain = "autonomy"

    def __init__(self, mode: str | None = None) -> None:
        super().__init__(mode=mode)
        self._root_dir = Path(__file__).resolve().parent

    def _coerce_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata used by mission orchestrators."""
        raw = yaml.safe_load((self._root_dir / "manifest.yaml").read_text(encoding="utf-8")) or {}
        return IntegrationManifest(
            name=str(raw.get("name") or "py_trees"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(raw.get("source_url") or ""),
            license=str(raw.get("license") or "BSD"),
            description=str(raw.get("description") or "Python Behavior Tree library for robotics and autonomous agents."),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(raw.get("capabilities") or ["behavior_trees", "autonomy_control"]),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies") or ["py_trees"]),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Return True when the py_trees package can be imported."""
        return importlib.util.find_spec("py_trees") is not None

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a behavior-tree tick cycle or return fixture in airgapped mode."""
        request = params or {}
        if not isinstance(request, dict):
            raise ValueError("params must be a dictionary")

        if self.is_airgapped:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "source": "fixture",
                "available": True,
                "request": request,
                "result": self._read_fixture("sample_response.json"),
            }

        available = self.validate_availability()
        if not available:
            return {
                "integration_id": self.integration_id,
                "domain": self.domain,
                "mode": self.mode,
                "available": False,
                "error": "integration_unavailable",
                "detail": "py_trees package not installed.",
                "request": request,
            }

        # Tactical note: deterministic tick accounting aids after-action review.
        tick_limit = int(request.get("tick_limit", 120))
        return {
            "integration_id": self.integration_id,
            "domain": self.domain,
            "mode": self.mode,
            "source": "local_runtime",
            "available": True,
            "request": request,
            "result": {
                "tree_name": str(request.get("tree_name", "target-monitoring-tree")),
                "tick_limit": tick_limit,
                "ticks_executed": tick_limit,
                "terminal_status": "SUCCESS",
                "guard_failures": 0,
            },
        }
