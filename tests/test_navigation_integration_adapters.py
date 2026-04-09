"""Unit tests for navigation integration wrappers used in tactical rehearsal."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NAVIGATION_ROOT = PROJECT_ROOT / "packages" / "integrations" / "navigation"

ADAPTER_SPECS = [
    (
        "lio-sam",
        "LioSamAdapter",
        "LIO-SAM",
        "https://github.com/TixiaoShan/LIO-SAM",
        "(BSD-style)",
    ),
    (
        "kr-autonomous-flight",
        "KrAutonomousFlightAdapter",
        "kr_autonomous_flight",
        "https://github.com/KumarRobotics/kr_autonomous_flight",
        "(BSD-style)",
    ),
    (
        "vins-fusion",
        "VinsFusionAdapter",
        "VINS-Fusion",
        "https://github.com/HKUST-Aerial-Robotics/VINS-Fusion",
        "(BSD-style)",
    ),
    (
        "openvins",
        "OpenvinsAdapter",
        "OpenVINS",
        "https://github.com/rpng/open_vins",
        "(BSD-style)",
    ),
    (
        "lio-sam-6axis",
        "LioSam6axisAdapter",
        "LIO_SAM_6AXIS",
        "https://github.com/JokerJohn/LIO_SAM_6AXIS",
        "(BSD-style)",
    ),
]


def _load_adapter_class(slug: str, class_name: str):
    module_path = NAVIGATION_ROOT / slug / "adapter.py"
    module_name = f"test_navigation_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize(
    ("slug", "class_name", "name", "source_url", "license_name"),
    ADAPTER_SPECS,
    ids=[slug for slug, *_ in ADAPTER_SPECS],
)
def test_manifest_is_loaded_from_yaml(
    slug: str,
    class_name: str,
    name: str,
    source_url: str,
    license_name: str,
) -> None:
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()

    manifest_yaml = NAVIGATION_ROOT / slug / "manifest.yaml"
    raw = yaml.safe_load(manifest_yaml.read_text(encoding="utf-8"))

    assert manifest.name == name
    assert manifest.slug == slug
    assert manifest.domain == "navigation"
    assert manifest.source_url == source_url
    assert manifest.license == license_name
    assert manifest.name == raw["name"]
    assert manifest.slug == raw["slug"]


@pytest.mark.parametrize(
    ("slug", "class_name", "name", "source_url", "license_name"),
    ADAPTER_SPECS,
    ids=[slug for slug, *_ in ADAPTER_SPECS],
)
def test_logger_name_matches_navigation_integration_slug(
    slug: str,
    class_name: str,
    name: str,
    source_url: str,
    license_name: str,
) -> None:
    del name, source_url, license_name
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.navigation.{slug}"


@pytest.mark.parametrize(
    ("slug", "class_name", "name", "source_url", "license_name"),
    ADAPTER_SPECS,
    ids=[slug for slug, *_ in ADAPTER_SPECS],
)
def test_airgapped_validate_and_execute_use_local_fixture(
    slug: str,
    class_name: str,
    name: str,
    source_url: str,
    license_name: str,
) -> None:
    del name, source_url, license_name
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")

    assert adapter.validate_availability() is True
    response = adapter.execute({"operation": "mission_rehearsal"})

    assert response["integration_id"] == slug
    assert response["domain"] == "navigation"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["available"] is True
    assert response["result"]["status"] == "completed"


@pytest.mark.parametrize(
    ("slug", "class_name", "name", "source_url", "license_name"),
    ADAPTER_SPECS,
    ids=[slug for slug, *_ in ADAPTER_SPECS],
)
def test_execute_rejects_non_mapping_params(
    slug: str,
    class_name: str,
    name: str,
    source_url: str,
    license_name: str,
) -> None:
    del name, source_url, license_name
    adapter_cls = _load_adapter_class(slug, class_name)
    adapter = adapter_cls(mode="airgapped")

    with pytest.raises(ValueError):
        adapter.execute(["unsafe", "params"])
