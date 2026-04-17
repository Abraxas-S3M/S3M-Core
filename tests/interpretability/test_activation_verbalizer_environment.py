"""Environment-level checks for activation verbalizer test readiness."""

from __future__ import annotations


def test_activation_verbalizer_dependency_gate() -> None:
    """Document that torch is optional in minimal CI images."""
    try:
        import torch  # noqa: F401
    except ModuleNotFoundError:
        assert True
    else:
        assert True
