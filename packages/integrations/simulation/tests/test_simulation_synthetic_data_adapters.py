from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


CASES = [
    ("ctgan", "CtganAdapter", "MIT", "sample"),
    ("doppelganger", "DoppelgangerAdapter", "(Open)", "sample_sequence"),
    ("tgan", "TganAdapter", "MIT", "sample"),
    ("datasynthesizer", "DatasynthesizerAdapter", "MIT", "generate"),
    ("awesome-synthetic-data", "AwesomeSyntheticDataAdapter", "MIT", "catalog_lookup"),
]


def _load_adapter(slug: str, class_name: str):
    adapter_path = Path(__file__).resolve().parents[1] / slug / "adapter.py"
    module_name = f"s3m_simulation_{slug.replace('-', '_')}_adapter_under_test"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize(("slug", "class_name", "license_name", "_operation"), CASES)
def test_manifest_metadata_is_loaded(
    slug: str, class_name: str, license_name: str, _operation: str
) -> None:
    adapter_cls = _load_adapter(slug, class_name)
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == slug
    assert manifest.domain == "simulation"
    assert manifest.license == license_name


@pytest.mark.parametrize(("slug", "class_name", "_license_name", "_operation"), CASES)
def test_validate_availability_true_in_airgapped_mode(
    slug: str, class_name: str, _license_name: str, _operation: str
) -> None:
    adapter_cls = _load_adapter(slug, class_name)
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize(("slug", "class_name", "_license_name", "operation"), CASES)
def test_execute_returns_fixture_when_airgapped(
    slug: str, class_name: str, _license_name: str, operation: str
) -> None:
    adapter_cls = _load_adapter(slug, class_name)
    response = adapter_cls(mode="airgapped").execute({"operation": operation})
    assert response["source"] == "fixture"
    assert response["integration_id"] == slug
    assert response["mode"] == "airgapped"
    assert isinstance(response["result"], dict)
    assert "snapshot_id" in response["result"]


@pytest.mark.parametrize(("slug", "class_name", "_license_name", "_operation"), CASES)
def test_logger_name_matches_simulation_slug(
    slug: str, class_name: str, _license_name: str, _operation: str
) -> None:
    adapter_cls = _load_adapter(slug, class_name)
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.simulation.{slug}"
