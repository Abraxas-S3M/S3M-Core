"""Unit tests for dashboard integration wrappers in tactical airgapped mode."""

from __future__ import annotations

import importlib

import pytest


CASES = [
    (
        "packages.integrations.dashboard.awesome-threat-detection-curated.adapter",
        "AwesomeThreatDetectioncuratedAdapter",
        "awesome-threat-detection-curated",
        "Awesome-Threat-Detection (Curated)",
        "https://github.com/0x4D31/awesome-threat-detection",
    ),
    (
        "packages.integrations.dashboard.rogueshield-ai-threat-detector.adapter",
        "RogueshieldAiThreatDetectorAdapter",
        "rogueshield-ai-threat-detector",
        "RogueShield AI Threat Detector",
        "https://github.com/mahaswetaroy1/rogueshield-ai-threat-detector",
    ),
    (
        "packages.integrations.dashboard.orbat-mapper.adapter",
        "OrbatMapperAdapter",
        "orbat-mapper",
        "Orbat-Mapper",
        "https://github.com/orbat-mapper/orbat-mapper",
    ),
    (
        "packages.integrations.dashboard.industrace.adapter",
        "IndustraceAdapter",
        "industrace",
        "Industrace",
        "https://github.com/industrace/industrace",
    ),
    (
        "packages.integrations.dashboard.marmotte.adapter",
        "MarmotteAdapter",
        "marmotte",
        "Marmotte",
        "https://github.com/marmotteio/marmotteio",
    ),
]


@pytest.mark.parametrize(("module_path", "class_name", "slug", "name", "source_url"), CASES)
def test_dashboard_adapters_manifest_and_airgapped_execution(
    module_path: str,
    class_name: str,
    slug: str,
    name: str,
    source_url: str,
) -> None:
    module = importlib.import_module(module_path)
    adapter_class = getattr(module, class_name)

    adapter = adapter_class(mode="airgapped")

    assert adapter.logger.name == f"s3m.integrations.dashboard.{slug}"
    assert adapter.validate_availability() is True

    manifest = adapter.get_manifest()
    assert manifest.name == name
    assert manifest.slug == slug
    assert manifest.domain == "dashboard"
    assert manifest.source_url == source_url
    assert manifest.license == "MIT"

    payload = adapter.execute({"operation": "status"})
    assert payload["integration_id"] == slug
    assert payload["mode"] == "airgapped"
    assert payload["source"] == "fixture"
    assert payload["params"] == {"operation": "status"}
    assert isinstance(payload["data"], dict)
    assert payload["data"]
