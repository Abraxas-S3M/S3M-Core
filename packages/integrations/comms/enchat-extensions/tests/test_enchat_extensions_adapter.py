from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_adapter():
    adapter_path = Path(__file__).resolve().parents[1] / "adapter.py"
    spec = importlib.util.spec_from_file_location("s3m_comms_enchat_extensions_adapter_under_test", adapter_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.EnchatextensionsAdapter


def test_manifest_metadata_is_loaded():
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "enchat-extensions"
    assert manifest.domain == "comms"
    assert manifest.license == "Unknown"


def test_validate_availability_true_in_airgapped_mode():
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute(
        {"operation": "relay_status", "session_id": "session-tf-spear-19", "relay_hops": 3}
    )
    assert response["source"] == "fixture"
    assert response["result"]["snapshot_id"] == "enchat-comms-2026-04-10-0600z"
