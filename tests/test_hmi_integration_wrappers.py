"""Unit tests for HMI integration wrappers.

Military/tactical context:
These tests ensure Human-Machine Teaming adapters remain deterministic in
airgapped environments required for sovereign mission rehearsal.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HMI_DIR = ROOT / "packages" / "integrations" / "hmi"

CASES: list[tuple[str, str, str, str]] = [
    (
        "vlms-with-ros2-workshop",
        "VlmsWithRos2WorkshopAdapter",
        "https://github.com/nilutpolkashyap/vlms_with_ros2_workshop",
        "vlms_with_ros2_workshop",
    ),
    (
        "vision-voice-multimodal-app",
        "VisionVoiceMultimodalAppAdapter",
        "https://github.com/EvanGks/vision-voice-multimodal-app",
        "vision-voice-multimodal-app",
    ),
    (
        "awesome-embodied-vla-va-vln",
        "AwesomeEmbodiedVlaVaAdapter",
        "https://github.com/jonyzhang2023/awesome-embodied-vla-va-vln",
        "awesome-embodied-vla-va-vln",
    ),
    (
        "awesome-multimodal-large-language-models",
        "AwesomeMultimodalLargeLanguageAdapter",
        "https://github.com/ZhanYang-nwpu/Awesome-Multimodal-Large-Language-Models-for-UAV-Vision-Language-Perception",
        "Awesome-Multimodal-Large-Language-Models-for-UAV",
    ),
    (
        "awesome-embodied-multimodal-llms",
        "AwesomeEmbodiedMultimodalLlmsAdapter",
        "https://github.com/tulerfeng/Awesome-Embodied-Multimodal-LLMs",
        "Awesome-Embodied-Multimodal-LLMs",
    ),
]


def _load_adapter_class(slug: str, class_name: str):
    adapter_path = HMI_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_hmi_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize(("slug", "class_name", "source_url", "manifest_name"), CASES)
def test_get_manifest_returns_expected_fields(
    slug: str, class_name: str, source_url: str, manifest_name: str
) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()

    assert manifest.name == manifest_name
    assert manifest.slug == slug
    assert manifest.domain == "hmi"
    assert manifest.source_url == source_url
    assert manifest.license == "MIT"
    assert manifest.integration_type == "adapter"
    assert adapter.logger.name == f"s3m.integrations.hmi.{slug}"


@pytest.mark.parametrize(("slug", "class_name", "_source_url", "_manifest_name"), CASES)
def test_validate_availability_uses_fixture_in_airgapped_mode(
    slug: str, class_name: str, _source_url: str, _manifest_name: str
) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")

    assert adapter.validate_availability() is True


@pytest.mark.parametrize(("slug", "class_name", "_source_url", "_manifest_name"), CASES)
def test_execute_returns_fixture_payload_in_airgapped_mode(
    slug: str, class_name: str, _source_url: str, _manifest_name: str
) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")

    response = adapter.execute({"operation": "status"})

    assert response["integration_id"] == slug
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["status"] == "ok"
    assert response["request"]["operation"] == "status"
    assert isinstance(response["result"], dict)
    assert response["result"]


@pytest.mark.parametrize(("slug", "class_name", "_source_url", "_manifest_name"), CASES)
def test_execute_rejects_non_mapping_params(
    slug: str, class_name: str, _source_url: str, _manifest_name: str
) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError):
        adapter.execute(["not", "a", "mapping"])  # type: ignore[arg-type]
