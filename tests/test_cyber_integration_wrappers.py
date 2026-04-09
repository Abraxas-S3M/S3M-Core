"""Tests for cyber integration wrappers under packages/integrations/cyber.

Military/tactical context:
These tests ensure defensive SOC adapters remain deterministic in airgapped
operations and reject malformed operator inputs before execution.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


_ROOT = Path(__file__).resolve().parents[1]

_ADAPTER_CASES = [
    {
        "slug": "wazuh-soc-lab",
        "class_name": "WazuhSocLabAdapter",
        "manifest_name": "Wazuh-SOC-Lab",
        "source_url": "https://github.com/marxgoo/Wazuh-SOC-Lab",
    },
    {
        "slug": "wazuh-soc-enterprise",
        "class_name": "WazuhSocEnterpriseAdapter",
        "manifest_name": "wazuh-soc-enterprise",
        "source_url": "https://github.com/brunoflausino/wazuh-soc-enterprise",
    },
    {
        "slug": "enterprise-soc-detection-and-response-wa",
        "class_name": "EnterpriseSocDetectionAndAdapter",
        "manifest_name": "Enterprise-SOC-Detection-and-Response-Wazuh",
        "source_url": "https://github.com/THeOLdMAn48/Enterprise-SOC-Detection-and-Response-Wazuh",
    },
    {
        "slug": "open-source-siem-soc-stack",
        "class_name": "OpenSourceSiemSocAdapter",
        "manifest_name": "Open-Source-SIEM_SOC-Stack",
        "source_url": "https://github.com/ArfanAbid/Open-Source-SIEM_SOC-Stack",
    },
    {
        "slug": "soc-toolkit",
        "class_name": "SocToolkitAdapter",
        "manifest_name": "soc-toolkit",
        "source_url": "https://github.com/phrp720/soc-toolkit",
    },
]


def _load_adapter_module(slug: str):
    module_path = _ROOT / "packages" / "integrations" / "cyber" / slug / "adapter.py"
    spec = importlib.util.spec_from_file_location(f"test_module_{slug.replace('-', '_')}", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("case", _ADAPTER_CASES)
def test_adapter_manifest_and_airgapped_fixture(case: dict[str, str]) -> None:
    module = _load_adapter_module(case["slug"])
    adapter_class = getattr(module, case["class_name"])
    adapter = adapter_class(mode="airgapped")

    manifest = adapter.get_manifest()
    assert manifest.name == case["manifest_name"]
    assert manifest.slug == case["slug"]
    assert manifest.domain == "cyber"
    assert manifest.source_url == case["source_url"]
    assert manifest.license == "Unknown"

    assert adapter.validate_availability() is True
    result = adapter.execute({"action": "status"})
    assert result["mode"] == "airgapped"
    assert result["source"] == "fixture"
    assert isinstance(result["data"], dict)
    assert result["data"] != {}


@pytest.mark.parametrize("case", _ADAPTER_CASES)
def test_adapter_rejects_invalid_actions_in_online_mode(case: dict[str, str], monkeypatch: Any) -> None:
    module = _load_adapter_module(case["slug"])
    adapter_class = getattr(module, case["class_name"])
    adapter = adapter_class(mode="online")

    monkeypatch.delenv("WAZUH_HOME", raising=False)
    monkeypatch.delenv("CALDERA_HOME", raising=False)
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    monkeypatch.delenv("SOC_TOOLKIT_HOME", raising=False)
    monkeypatch.setattr(module.shutil, "which", lambda _: None)

    response = adapter.execute({"action": "unsupported"})
    assert response["ok"] is False
    assert response["error"] == "invalid_action"
    assert "allowed_actions" in response

    assert adapter.validate_availability() is False
