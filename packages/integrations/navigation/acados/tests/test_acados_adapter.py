from __future__ import annotations

from packages.integrations.navigation.acados.adapter import AcadosAdapter


def test_manifest_metadata_is_loaded() -> None:
    manifest = AcadosAdapter(mode="airgapped").get_manifest()
    assert manifest.slug == "acados"
    assert manifest.domain == "navigation"
    assert manifest.license == "BSD"


def test_validate_availability_true_in_airgapped_mode() -> None:
    assert AcadosAdapter(mode="airgapped").validate_availability() is True


def test_execute_returns_fixture_when_airgapped() -> None:
    response = AcadosAdapter(mode="airgapped").execute({"operation": "solve_nmpc"})
    assert response["source"] == "fixture"
    assert response["result"]["controller"] == "nonlinear_mpc"
