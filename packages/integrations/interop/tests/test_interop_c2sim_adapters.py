from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


CASES = [
    {
        "adapter_path": "openc2sim.github.io/adapter.py",
        "class_name": "Openc2simgithubioAdapter",
        "slug": "openc2sim.github.io",
        "fixture_key": "reference_bundle",
    },
    {
        "adapter_path": "msg201cwix/adapter.py",
        "class_name": "Msg201cwixAdapter",
        "slug": "msg201cwix",
        "fixture_key": "exercise_id",
    },
    {
        "adapter_path": "c2sim/adapter.py",
        "class_name": "C2simAdapter",
        "slug": "c2sim",
        "fixture_key": "exchange_id",
    },
    {
        "adapter_path": "simplec2sim/adapter.py",
        "class_name": "Simplec2simAdapter",
        "slug": "simplec2sim",
        "fixture_key": "simulation_id",
    },
    {
        "adapter_path": "msdllib/adapter.py",
        "class_name": "MsdllibAdapter",
        "slug": "msdllib",
        "fixture_key": "parse_job_id",
    },
]


def _load_adapter_class(adapter_path: str, class_name: str):
    root = Path(__file__).resolve().parents[1]
    source = root / adapter_path
    module_name = f"s3m_interop_adapter_{class_name.lower()}"
    spec = importlib.util.spec_from_file_location(module_name, source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", CASES, ids=[case["slug"] for case in CASES])
def test_manifest_metadata_is_loaded(case: dict[str, str]):
    adapter_cls = _load_adapter_class(case["adapter_path"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()
    assert manifest.slug == case["slug"]
    assert manifest.domain == "interop"
    assert manifest.license == "Unknown"
    assert adapter.logger.name == f"s3m.integrations.interop.{case['slug']}"


@pytest.mark.parametrize("case", CASES, ids=[case["slug"] for case in CASES])
def test_validate_availability_true_in_airgapped_mode(case: dict[str, str]):
    adapter_cls = _load_adapter_class(case["adapter_path"], case["class_name"])
    assert adapter_cls(mode="airgapped").validate_availability() is True


@pytest.mark.parametrize("case", CASES, ids=[case["slug"] for case in CASES])
def test_execute_returns_fixture_when_airgapped(case: dict[str, str]):
    adapter_cls = _load_adapter_class(case["adapter_path"], case["class_name"])
    response = adapter_cls(mode="airgapped").execute({"operation": "interop_rehearsal"})
    assert response["source"] == "fixture"
    assert case["fixture_key"] in response["result"]
