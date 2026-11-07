"""Le Chonk orchestrator routing and rollback tests."""

from __future__ import annotations

import os

import pytest

from src.integrations.lechonk.flags import lechonk_enabled
from src.integrations.lechonk.orchestrator_routing import (
    configured_planning_binding,
    resolve_planning_backing_engine,
)

REPO_ROOT = pytest.importorskip("pathlib").Path(__file__).resolve().parents[3]
ENGINES = str(REPO_ROOT / "configs" / "engines.yaml")


def test_planning_stays_on_legacy_mistral_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("S3M_LECHONK_ENABLED", raising=False)
    decision = resolve_planning_backing_engine(engines_path=ENGINES)
    assert decision.used_lechonk is False
    assert decision.backing_engine_id == "mistral"
    assert decision.fallback_reason


def test_quad_map_still_binds_planning_to_mistral() -> None:
    assert configured_planning_binding(ENGINES) == "mistral"


def test_lechonk_flag_without_execution_stays_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3M_LECHONK_ENABLED", "true")
    assert lechonk_enabled() is False
    decision = resolve_planning_backing_engine(engines_path=ENGINES)
    assert decision.used_lechonk is False
