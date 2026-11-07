"""Status reporting and deployment profile scheduler tests."""

from __future__ import annotations

import pytest

from src.integrations.lechonk.deployment_profiles import DeploymentProfile
from src.integrations.lechonk.scheduler import select_deployment_profile
from src.integrations.lechonk.status import ReadinessPhase, compute_planning_readiness


def test_readiness_reports_fallback_by_default() -> None:
    readiness = compute_planning_readiness()
    assert readiness.phase in {ReadinessPhase.FALLBACK, ReadinessPhase.QUARANTINED}
    assert readiness.fallback_engine_id == "mistral"
    assert readiness.feature_flag_enabled is False


def test_scheduler_never_selects_cpu_gguf_for_unverified_1t() -> None:
    selection = select_deployment_profile(force_fallback=True)
    assert selection.selected == DeploymentProfile.FALLBACK_SMALL_MODEL
    assert not selection.uses_lechonk_weights()
