"""awesome-incident-response integration adapter for defensive cyber operations.

Military/tactical context:
This wrapper provides a structured catalog of response tooling and references so
SOC teams can sustain defensive tempo during incidents with limited connectivity.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

import yaml

from packages.integrations.base import IntegrationAdapter, IntegrationManifest


class AwesomeIncidentResponseAdapter(IntegrationAdapter):
    """Adapter for curated incident-response resources and tooling references."""

    integration_id = "awesome-incident-response"
    domain = "cyber"

    def _manifest_path(self) -> Path:
        return Path(__file__).resolve().parent / "manifest.yaml"

    def _coerce_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    def _load_manifest_mapping(self) -> dict[str, Any]:
        raw = yaml.safe_load(self._manifest_path().read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("awesome-incident-response manifest must contain a YAML mapping.")
        return raw

    def _resolve_repo_path(self) -> Path | None:
        env_key = f"{self.integration_id.upper().replace('-', '_')}_REPO_PATH"
        explicit = self._env(env_key)
        if explicit:
            return Path(explicit).expanduser()
        vendor_root = self._env("INTEGRATION_VENDOR_ROOT")
        if vendor_root:
            return Path(vendor_root).expanduser() / self.integration_id
        return None

    def get_manifest(self) -> IntegrationManifest:
        """Load integration metadata from manifest.yaml for mission registry use."""
        raw = self._load_manifest_mapping()
        return IntegrationManifest(
            name=str(raw.get("name") or "awesome-incident-response"),
            slug=str(raw.get("slug") or self.integration_id),
            domain=str(raw.get("domain") or self.domain),
            source_url=str(
                raw.get("source_url")
                or "https://github.com/meirwah/awesome-incident-response"
            ),
            license=str(raw.get("license") or "Unknown"),
            description=str(
                raw.get("description")
                or "Curated tooling and resource references for incident responders."
            ),
            integration_type=str(raw.get("integration_type") or "adapter"),
            capabilities=self._coerce_list(
                raw.get("capabilities")
                or ["resource-catalog", "incident-response", "tool-selection"]
            ),
            pip_dependencies=self._coerce_list(raw.get("pip_dependencies")),
            system_dependencies=self._coerce_list(raw.get("system_dependencies")),
            docker_dependencies=self._coerce_list(raw.get("docker_dependencies")),
            airgapped_support=bool(raw.get("airgapped_support", True)),
            vendor_path=str(raw.get("vendor_path") or ""),
        )

    def validate_availability(self) -> bool:
        """Validate local readiness without external network dependencies."""
        fixture_available = bool(self._read_fixture("sample_response.json"))
        repo_path = self._resolve_repo_path()
        repo_available = bool(repo_path and repo_path.exists() and repo_path.is_dir())
        git_available = shutil.which("git") is not None
        if self.is_airgapped:
            return fixture_available
        return repo_available or git_available

    def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute tactical resource discovery for SOC teams."""
        params = params or {}
        if not isinstance(params, dict):
            return {
                "status": "error",
                "error": "invalid_params",
                "detail": "params must be a mapping.",
                "integration_id": self.integration_id,
            }

        query = str(params.get("query", "")).strip().lower()
        category = str(params.get("category", "")).strip().lower()
        try:
            limit = int(params.get("limit", 10))
        except (TypeError, ValueError):
            return {
                "status": "error",
                "error": "invalid_limit_type",
                "detail": "limit must be an integer.",
                "integration_id": self.integration_id,
            }
        if limit < 1 or limit > 1000:
            return {
                "status": "error",
                "error": "invalid_limit_range",
                "detail": "limit must be between 1 and 1000.",
                "integration_id": self.integration_id,
            }

        if self.is_airgapped:
            payload = self._read_fixture("sample_response.json")
            entries = payload.get("entries", []) if isinstance(payload, dict) else []
            if not isinstance(entries, list):
                entries = []
            if query:
                entries = [
                    item
                    for item in entries
                    if query in str(item.get("title", "")).lower()
                    or query in str(item.get("summary", "")).lower()
                    or any(query in str(tag).lower() for tag in item.get("tags", []))
                ]
            if category:
                entries = [
                    item
                    for item in entries
                    if category == str(item.get("category", "")).lower()
                ]
            return {
                **(payload if isinstance(payload, dict) else {}),
                "integration_id": self.integration_id,
                "mode": "airgapped",
                "query": query or None,
                "category": category or None,
                "returned": len(entries[:limit]),
                "entries": entries[:limit],
            }

        repo_path = self._resolve_repo_path()
        if not repo_path or not repo_path.exists():
            env_key = f"{self.integration_id.upper().replace('-', '_')}_REPO_PATH"
            return {
                "status": "error",
                "error": "repository_unavailable",
                "detail": f"Set {env_key} or INTEGRATION_VENDOR_ROOT to a local checkout path.",
                "integration_id": self.integration_id,
                "mode": "online",
            }

        entries: list[dict[str, Any]] = []
        for file_path in sorted(repo_path.rglob("*.md")):
            relative_path = str(file_path.relative_to(repo_path))
            if query and query not in relative_path.lower():
                continue
            entries.append(
                {
                    "title": file_path.stem.replace("-", " ").replace("_", " ").title(),
                    "relative_path": relative_path,
                    "source": "local_repository",
                }
            )
            if len(entries) >= limit:
                break

        return {
            "status": "ok",
            "integration_id": self.integration_id,
            "mode": "online",
            "query": query or None,
            "category": category or None,
            "returned": len(entries),
            "entries": entries,
            "source_repo": str(repo_path),
        }

