"""Unit tests for secure communications integration wrappers.

Military/tactical context:
These tests ensure comms adapters provide deterministic airgapped behavior for
mission messaging workflows when networks are denied or disconnected.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

from packages.integrations.base import IntegrationManifest


ROOT = Path(__file__).resolve().parents[1]
COMMS_DIR = ROOT / "packages" / "integrations" / "comms"

CASES: list[dict[str, str]] = [
    {
        "slug": "synapse-matrix-homeserver",
        "class_name": "SynapsematrixHomeserverAdapter",
        "name": "synapse (Matrix homeserver)",
        "source_url": "https://github.com/element-hq/synapse",
        "license": "Unknown",
    },
    {
        "slug": "berty",
        "class_name": "BertyAdapter",
        "name": "berty",
        "source_url": "https://github.com/berty/berty",
        "license": "Unknown",
    },
    {
        "slug": "simplex-chat",
        "class_name": "SimplexChatAdapter",
        "name": "simplex-chat",
        "source_url": "https://github.com/simplex-chat/simplex-chat",
        "license": "Unknown",
    },
    {
        "slug": "meshtastic",
        "class_name": "MeshtasticAdapter",
        "name": "meshtastic",
        "source_url": "https://github.com/meshtastic/meshtastic",
        "license": "Unknown",
    },
    {
        "slug": "tfc-tinfoil-chat",
        "class_name": "TfctinfoilChatAdapter",
        "name": "tfc (Tinfoil Chat)",
        "source_url": "https://github.com/maqp/tfc",
        "license": "Unknown",
    },
]


def _load_adapter_class(slug: str, class_name: str) -> type[Any]:
    adapter_path = COMMS_DIR / slug / "adapter.py"
    module_name = f"tests.dynamic_comms_{slug.replace('-', '_')}_adapter"
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, class_name)


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_manifest_fields(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    manifest = adapter.get_manifest()
    raw = yaml.safe_load((COMMS_DIR / case["slug"] / "manifest.yaml").read_text(encoding="utf-8"))

    assert isinstance(manifest, IntegrationManifest)
    assert manifest.name == case["name"]
    assert manifest.name == raw["name"]
    assert manifest.slug == case["slug"]
    assert manifest.slug == raw["slug"]
    assert manifest.domain == "comms"
    assert manifest.domain == raw["domain"]
    assert manifest.source_url == case["source_url"]
    assert manifest.source_url == raw["source_url"]
    assert manifest.license == case["license"]
    assert manifest.license == raw["license"]
    assert manifest.integration_type == "adapter"
    assert manifest.airgapped_support is True


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_logger_names_follow_comms_slug(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == f"s3m.integrations.comms.{case['slug']}"


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_validate_availability_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    assert adapter.validate_availability() is True


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_execute_returns_fixture_in_airgapped_mode(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")

    response = adapter.execute({"operation": "comms_readiness_check", "priority": "high"})

    assert response["integration_id"] == case["slug"]
    assert response["domain"] == "comms"
    assert response["mode"] == "airgapped"
    assert response["source"] == "fixture"
    assert response["status"] == "ok"
    assert response["operation"] == "comms_readiness_check"
    assert response["request"]["priority"] == "high"
    assert isinstance(response["result"], dict)
    assert response["result"]


@pytest.mark.parametrize("case", CASES, ids=[item["slug"] for item in CASES])
def test_execute_rejects_non_mapping_params(case: dict[str, str]) -> None:
    adapter_cls = _load_adapter_class(case["slug"], case["class_name"])
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="dictionary"):
        adapter.execute(params=["invalid"])  # type: ignore[arg-type]
