from __future__ import annotations

import importlib

import pytest


def _load_adapter():
    module = importlib.import_module("packages.integrations.nato.acados-optimal-control-solver.adapter")
    return module.AcadosoptimalControlSolverAdapter


def test_manifest_metadata_is_loaded():
    adapter_cls = _load_adapter()
    manifest = adapter_cls(mode="airgapped").get_manifest()
    assert manifest.slug == "acados-optimal-control-solver"
    assert manifest.domain == "nato"
    assert manifest.license == "BSD"


def test_validate_availability_true_in_airgapped_mode():
    adapter_cls = _load_adapter()
    assert adapter_cls(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped():
    adapter_cls = _load_adapter()
    response = adapter_cls(mode="airgapped").execute({"operation": "trajectory_optimization"})
    assert response["source"] == "fixture"
    assert response["result"]["solver"]["name"] == "acados"


def test_logger_name_uses_required_nato_prefix():
    adapter_cls = _load_adapter()
    adapter = adapter_cls(mode="airgapped")
    assert adapter.logger.name == "s3m.integrations.nato.acados-optimal-control-solver"


def test_execute_rejects_unsupported_operation():
    adapter_cls = _load_adapter()
    adapter = adapter_cls(mode="airgapped")
    with pytest.raises(ValueError, match="Unsupported operation"):
        adapter.execute({"operation": "invalid_trajectory_mode"})
