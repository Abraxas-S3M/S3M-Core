"""Unit tests for autonomy integration adapters.

Military/tactical context:
These tests ensure autonomy wrappers remain deterministic in airgapped mode,
which is required for offline mission rehearsal and validation.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest


CASES: list[tuple[str, str, str]] = [
    ("packages.integrations.autonomy.pettingzoo.adapter", "PettingzooAdapter", "pettingzoo"),
    (
        "packages.integrations.autonomy.rl-baselines3-zoo.adapter",
        "RlBaselines3ZooAdapter",
        "rl-baselines3-zoo",
    ),
    ("packages.integrations.autonomy.eli5.adapter", "Eli5Adapter", "eli5"),
    ("packages.integrations.autonomy.interpretml.adapter", "InterpretmlAdapter", "interpretml"),
]


def _load_adapter(module_path: str, class_name: str) -> Any:
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


@pytest.mark.parametrize(("module_path", "class_name", "slug"), CASES)
def test_manifest_loading(module_path: str, class_name: str, slug: str) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    manifest = adapter.get_manifest()
    assert manifest.slug == slug
    assert manifest.domain == "autonomy"
    assert manifest.license == "MIT"
    assert manifest.name


@pytest.mark.parametrize(("module_path", "class_name", "slug"), CASES)
def test_validate_availability_returns_boolean(module_path: str, class_name: str, slug: str) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    result = adapter.validate_availability()
    assert isinstance(result, bool)
    assert result is True
    assert adapter.integration_id == slug


@pytest.mark.parametrize(("module_path", "class_name", "slug"), CASES)
def test_execute_returns_fixture_payload_in_airgapped_mode(module_path: str, class_name: str, slug: str) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    payload = adapter.execute({"action": "describe"})
    assert payload["mode"] == "airgapped"
    assert payload["source"] == "fixture"
    assert payload["integration_id"] == slug
    assert payload["status"] in {"ok", "planned"}


@pytest.mark.parametrize(("module_path", "class_name", "_slug"), CASES)
def test_execute_rejects_non_mapping_params(module_path: str, class_name: str, _slug: str) -> None:
    adapter_cls = _load_adapter(module_path, class_name)
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError):
        adapter.execute(["not", "a", "mapping"])  # type: ignore[arg-type]
