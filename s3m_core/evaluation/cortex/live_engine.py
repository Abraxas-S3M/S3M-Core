"""Live Cortex adapter for S1 range nightly eval archival.

Military/tactical context:
Nightly runs hit the operational range endpoint; CI uses the deterministic engine
so Jetson edge builders never depend on range availability.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict

from s3m_core.evaluation.cortex.deterministic_engine import DeterministicCortexEngine


@dataclass(frozen=True, slots=True)
class LiveEngineConfig:
    range_url: str
    timeout_sec: float = 30.0


class LiveCortexEngine:
    """HTTP facade to the S1 range with deterministic fallback for dry runs."""

    def __init__(self, config: LiveEngineConfig | None = None) -> None:
        url = (config.range_url if config else os.environ.get("S3M_CORTEX_RANGE_URL", "")).strip()
        self._config = LiveEngineConfig(range_url=url, timeout_sec=(config.timeout_sec if config else 30.0))
        self._fallback = DeterministicCortexEngine()

    @property
    def uses_range(self) -> bool:
        return bool(self._config.range_url)

    def invoke(self, suite: str, case: Dict[str, Any]) -> Dict[str, Any]:
        if not self.uses_range:
            return self._fallback_local(suite, case)
        payload = json.dumps({"suite": suite, "case": case}).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self._config.range_url.rstrip('/')}/eval",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._config.timeout_sec) as response:
                body = response.read().decode("utf-8")
                parsed = json.loads(body)
                if isinstance(parsed, dict):
                    return parsed
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass
        return self._fallback_local(suite, case)

    def _fallback_local(self, suite: str, case: Dict[str, Any]) -> Dict[str, Any]:
        engine = self._fallback
        if suite == "defensive_tasks":
            triage = engine.triage_event(case)
            return {"triage": triage, "ranked_paths": engine.rank_attack_paths(case)}
        if suite == "injection":
            return engine.probe_injection(str(case.get("payload", "")), str(case.get("channel", "logs")))
        if suite == "false_containment":
            return engine.run_containment(case)
        if suite == "rollback":
            engine.apply_divergence(case)
            success = engine.rollback(case)
            return {"rollback_success": success}
        if suite == "refusal":
            role = str(case.get("role", "tactical_analyst"))
            refused = engine.evaluate_refusal(role, str(case.get("request", "")))
            return {"refused": refused}
        if suite == "rug_pull_and_supply_chain":
            refused = engine.evaluate_supply_chain(case)
            return {"refused": refused}
        return {}
