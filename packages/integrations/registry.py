"""Discovery utilities for S3M integration manifests."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from packages.integrations.base import IntegrationManifest


LOGGER = logging.getLogger(__name__)
INTEGRATIONS_ROOT = Path(__file__).resolve().parent


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _load_manifest(manifest_path: Path) -> IntegrationManifest | None:
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        LOGGER.exception("Skipping invalid manifest YAML: %s", manifest_path)
        return None

    if not isinstance(raw, dict):
        LOGGER.warning("Skipping non-mapping manifest file: %s", manifest_path)
        return None

    domain = str(raw.get("domain") or manifest_path.parent.parent.name)
    slug = str(raw.get("slug") or manifest_path.parent.name)
    return IntegrationManifest(
        name=str(raw.get("name") or slug),
        slug=slug,
        domain=domain,
        source_url=str(raw.get("source_url") or ""),
        license=str(raw.get("license") or "unknown"),
        description=str(raw.get("description") or ""),
        integration_type=str(raw.get("integration_type") or "adapter"),
        capabilities=_coerce_list(raw.get("capabilities")),
        pip_dependencies=_coerce_list(raw.get("pip_dependencies")),
        system_dependencies=_coerce_list(raw.get("system_dependencies")),
        docker_dependencies=_coerce_list(raw.get("docker_dependencies")),
        airgapped_support=bool(raw.get("airgapped_support", True)),
        vendor_path=str(raw.get("vendor_path") or ""),
    )


def discover_integration_manifests(root_dir: Path | None = None) -> list[IntegrationManifest]:
    """Scan all integration domains and return parsed manifest entries."""

    root = root_dir or INTEGRATIONS_ROOT
    manifests: list[IntegrationManifest] = []
    for domain_dir in sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith("_")):
        for manifest_path in sorted(domain_dir.rglob("manifest.yaml")):
            manifest = _load_manifest(manifest_path)
            if manifest is not None:
                manifests.append(manifest)
    return manifests
