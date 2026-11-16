"""Eval reports must state which backend actually answered.

Military/tactical context:
A nightly "live" readiness number that was silently produced by the deterministic
fixture engine would overstate operational readiness to commanders and partners.
These tests pin the provenance fields so that cannot regress.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from s3m_core.evaluation.cortex.live_engine import LiveCortexEngine, LiveEngineConfig
from s3m_core.evaluation.cortex.suite_runner import CortexSuiteRunner

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.cortex


def test_live_engine_without_range_counts_fallback() -> None:
    engine = LiveCortexEngine(LiveEngineConfig(range_url=""))
    engine.invoke("refusal", {"role": "tactical_analyst", "request": "summarise alert"})
    assert engine.fallback_calls == 1
    assert engine.range_calls_ok == 0
    assert engine.effective_backend == "deterministic-fallback"


def test_live_engine_unreachable_range_counts_fallback() -> None:
    # Port 9 on loopback is discard/closed: the call fails fast and must be recorded.
    engine = LiveCortexEngine(LiveEngineConfig(range_url="http://127.0.0.1:9", timeout_sec=0.5))
    engine.invoke("refusal", {"role": "tactical_analyst", "request": "summarise alert"})
    assert engine.effective_backend == "deterministic-fallback"


def test_report_labels_deterministic_and_live_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("S3M_CORTEX_RANGE_URL", raising=False)
    runner = CortexSuiteRunner(ROOT / "evals" / "cortex", repo_root=ROOT)

    det = runner.run_all(mode="deterministic")
    assert det.effective_backend == "deterministic-fixtures"

    live = runner.run_all(mode="live")
    assert live.mode == "live"
    assert live.effective_backend == "deterministic-fallback"
    assert live.fallback_calls > 0 and live.range_calls_ok == 0
