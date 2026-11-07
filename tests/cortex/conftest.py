"""Cortex test hooks — lab crypto when liboqs is absent on the runner."""

from __future__ import annotations

import importlib

import pytest


def _policy_mod():
    return importlib.import_module("src.security.quantum.policy")


@pytest.fixture(autouse=True)
def _lab_mode_without_liboqs(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _policy_mod()
    mod.reset_quantum_policy_cache()
    if not mod.liboqs_available():
        monkeypatch.setenv("S3M_CRYPTO_MODE", "lab")
    yield
    mod.reset_quantum_policy_cache()
