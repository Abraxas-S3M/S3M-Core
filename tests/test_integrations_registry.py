"""Tests for S3M integration manifest discovery registry."""

from __future__ import annotations

from pathlib import Path

from packages.integrations.registry import discover_integration_manifests


def _write_manifest(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_discover_integration_manifests_loads_domain_entries(tmp_path) -> None:
    root = tmp_path / "integrations"
    _write_manifest(
        root / "autonomy" / "path_planner" / "manifest.yaml",
        """
name: Tactical Path Planner
slug: tactical-path-planner
domain: autonomy
source_url: https://github.com/example/path-planner
license: Apache-2.0
description: Planner adapter for contested route generation.
integration_type: adapter
capabilities:
  - route_generation
pip_dependencies:
  - networkx
airgapped_support: true
vendor_path: vendors/path_planner
""".strip(),
    )
    _write_manifest(
        root / "cyber" / "ioc_enricher" / "manifest.yaml",
        """
name: IOC Enricher
slug: ioc-enricher
domain: cyber
source_url: https://github.com/example/ioc-enricher
license: MIT
description: Enriches threat indicators with local datasets.
integration_type: service
capabilities:
  - enrichment
""".strip(),
    )

    manifests = discover_integration_manifests(root)
    by_slug = {manifest.slug: manifest for manifest in manifests}

    assert len(manifests) == 2
    assert by_slug["tactical-path-planner"].domain == "autonomy"
    assert by_slug["tactical-path-planner"].integration_type == "adapter"
    assert by_slug["tactical-path-planner"].pip_dependencies == ["networkx"]
    assert by_slug["ioc-enricher"].domain == "cyber"
    assert by_slug["ioc-enricher"].capabilities == ["enrichment"]


def test_discover_integration_manifests_uses_safe_defaults(tmp_path) -> None:
    root = tmp_path / "integrations"
    _write_manifest(
        root / "navigation" / "terrain_nav" / "manifest.yaml",
        """
description: Terrain navigation helper.
""".strip(),
    )

    manifests = discover_integration_manifests(root)
    assert len(manifests) == 1
    manifest = manifests[0]
    assert manifest.slug == "terrain_nav"
    assert manifest.domain == "navigation"
    assert manifest.integration_type == "adapter"
    assert manifest.license == "unknown"
    assert manifest.airgapped_support is True


def test_discover_integration_manifests_skips_invalid_yaml(tmp_path) -> None:
    root = tmp_path / "integrations"
    _write_manifest(root / "intel" / "bad_manifest" / "manifest.yaml", "{invalid: [")

    manifests = discover_integration_manifests(root)
    assert manifests == []
