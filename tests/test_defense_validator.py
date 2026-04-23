"""Unit tests for defense layer validation reporting."""

from __future__ import annotations

from s3m_core.defense.testing.defense_validator import DefenseValidator


def _all_probe_ids() -> list[str]:
    probe_ids: list[str] = []
    for tests in DefenseValidator.LAYER_MATRIX.values():
        for probe_id, _, _ in tests:
            probe_ids.append(probe_id)
    return probe_ids


def test_validate_all_passes_when_all_probes_true() -> None:
    overrides = {probe_id: True for probe_id in _all_probe_ids()}
    validator = DefenseValidator(probe_overrides=overrides)

    report = validator.validate_all()

    assert report.layers_tested == 9
    assert report.layers_passed == 9
    assert report.layers_failed == 0
    assert sorted(report.details) == [f"L{index}" for index in range(9)]
    assert all(layer_validation.passed for layer_validation in report.details.values())


def test_validate_all_marks_layer_failed_when_probe_fails() -> None:
    overrides = {probe_id: True for probe_id in _all_probe_ids()}
    overrides["l2.dns_nxdomain"] = False
    validator = DefenseValidator(probe_overrides=overrides)

    report = validator.validate_all()

    assert report.layers_passed == 8
    assert report.layers_failed == 1
    assert report.details["L2"].passed is False
    assert "Verify DNS returns NXDOMAIN for unlisted domains" in report.details["L2"].failures


def test_validate_all_captures_probe_exception_as_failure() -> None:
    overrides = {probe_id: True for probe_id in _all_probe_ids()}
    overrides["l5.mtls_required"] = lambda: (_ for _ in ()).throw(RuntimeError("probe exploded"))
    validator = DefenseValidator(probe_overrides=overrides)

    report = validator.validate_all()

    assert report.details["L5"].passed is False
    assert any("RuntimeError" in note for note in report.details["L5"].notes)
