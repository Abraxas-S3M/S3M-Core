"""
S3M Offline Brain — Autonomous Decision-Making Without Connectivity
====================================================================
When network links are severed, this module provides autonomous
decision capability using locally cached models, doctrine-informed
rules, and tactical heuristics suitable for denied environments.
"""

from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ConnectivityState(str, Enum):
    FULL = "full"
    DEGRADED = "degraded"
    INTERMITTENT = "intermittent"
    OFFLINE = "offline"


class OfflineConfig(BaseModel):
    """Configuration for offline decision behavior."""

    max_decision_queue: int = Field(default=500, ge=10)
    heuristic_confidence_cap: float = Field(default=0.6, ge=0.1, le=1.0)
    stale_model_penalty: float = Field(default=0.1, ge=0.0, le=0.5)
    max_offline_hours: float = Field(default=72.0, gt=0.0)
    sync_batch_size: int = Field(default=50, ge=1)
    decision_timeout_ms: float = Field(default=200.0, gt=0.0)


class OfflineDecision(BaseModel):
    """A tactical decision produced during degraded/offline operation."""

    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    action: str
    confidence: float = Field(ge=0.0, le=1.0)
    method: str = "heuristic"  # heuristic | cached_model | rule_based
    connectivity_state: ConnectivityState = ConnectivityState.OFFLINE
    rationale_en: str = ""
    rationale_ar: str = ""
    synced: bool = False
    priority: int = Field(default=5, ge=1, le=10)


class OfflineBrain:
    """
    Edge autonomy kernel for denied-connectivity mission continuity.

    Decision strategy order:
    1) Cached model inference
    2) Rule-based tactical doctrine
    3) Heuristic fallback
    """

    TACTICAL_RULES = {
        "threat_close_high_conf": {"action": "evade", "confidence": 0.8},
        "threat_close_low_conf": {"action": "hold", "confidence": 0.5},
        "threat_far_high_conf": {"action": "recon", "confidence": 0.7},
        "threat_far_low_conf": {"action": "advance", "confidence": 0.6},
        "no_threat": {"action": "advance", "confidence": 0.7},
        "fuel_critical": {"action": "rtb", "confidence": 0.9},
        "comms_lost": {"action": "hold", "confidence": 0.5},
    }

    def __init__(self, config: Optional[OfflineConfig] = None) -> None:
        self.config = config or OfflineConfig()
        self._connectivity = ConnectivityState.FULL
        self._decision_queue: Deque[OfflineDecision] = deque(maxlen=self.config.max_decision_queue)
        self._pending_sync: List[OfflineDecision] = []
        self._cached_model: Optional[Any] = None
        self._offline_since: Optional[float] = None
        self._lock = threading.Lock()

    def set_connectivity(self, state: ConnectivityState) -> None:
        """Update connectivity state and track offline interval."""
        if not isinstance(state, ConnectivityState):
            raise TypeError("state must be a ConnectivityState")
        with self._lock:
            prev = self._connectivity
            self._connectivity = state
            if state == ConnectivityState.OFFLINE and prev != ConnectivityState.OFFLINE:
                self._offline_since = time.time()
            elif state == ConnectivityState.FULL:
                self._offline_since = None

    def set_cached_model(self, model: Any) -> None:
        """Set a locally cached model that exposes predict(observation)."""
        self._cached_model = model

    def decide(
        self,
        observation: Dict[str, Any],
        available_actions: Optional[List[str]] = None,
    ) -> OfflineDecision:
        """
        Make a tactical decision using best available method.

        Tries cached model, then doctrine rules, then heuristic fallback.
        """
        if not isinstance(observation, dict):
            raise TypeError("observation must be a dictionary")
        actions = available_actions or ["advance", "hold", "retreat", "evade", "recon", "rtb"]
        if not actions:
            raise ValueError("available_actions must not be empty")

        if self._cached_model and hasattr(self._cached_model, "predict"):
            cached_decision = self._cached_model_decision(observation, actions)
            if cached_decision is not None:
                self._enqueue(cached_decision)
                return cached_decision

        rule_decision = self._rule_based_decision(observation, actions)
        if rule_decision is not None:
            self._enqueue(rule_decision)
            return rule_decision

        heuristic = self._heuristic_decision(observation, actions)
        self._enqueue(heuristic)
        return heuristic

    def _cached_model_decision(
        self,
        observation: Dict[str, Any],
        actions: List[str],
    ) -> Optional[OfflineDecision]:
        try:
            pred = self._cached_model.predict(observation)  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("Cached model failed during offline inference: %s", exc)
            return None

        action = "hold"
        confidence = 0.5
        if isinstance(pred, dict):
            action = str(pred.get("action", "hold"))
            confidence = float(pred.get("confidence", 0.5))

        if action not in actions:
            action = "hold" if "hold" in actions else actions[0]

        confidence = self._sanitize_confidence(confidence)

        if self._offline_since is not None:
            hours_offline = (time.time() - self._offline_since) / 3600.0
            stale_factor = max(0.3, 1.0 - self.config.stale_model_penalty * hours_offline)
            confidence *= stale_factor
            if hours_offline > self.config.max_offline_hours:
                confidence *= 0.8

        confidence = min(confidence, self.config.heuristic_confidence_cap + 0.2)

        return OfflineDecision(
            action=action,
            confidence=confidence,
            method="cached_model",
            connectivity_state=self._connectivity,
            rationale_en=f"Cached model selected '{action}' for tactical continuity.",
            rationale_ar=f"Cached model selected '{action}' for tactical continuity.",
        )

    def _rule_based_decision(
        self,
        observation: Dict[str, Any],
        actions: List[str],
    ) -> Optional[OfflineDecision]:
        """Apply doctrine-derived tactical rules for denied comms operations."""
        threat_distance = self._safe_float(observation.get("nearest_threat_distance", 999.0), default=999.0)
        threat_confidence = self._safe_float(observation.get("threat_confidence", 0.0), default=0.0)
        fuel_level = self._safe_float(observation.get("fuel_pct", 100.0), default=100.0)
        has_comms = bool(observation.get("comms_active", True))

        if fuel_level < 15.0:
            rule_key = "fuel_critical"
        elif not has_comms:
            rule_key = "comms_lost"
        elif threat_distance < 50.0 and threat_confidence > 0.7:
            rule_key = "threat_close_high_conf"
        elif threat_distance < 50.0:
            rule_key = "threat_close_low_conf"
        elif threat_confidence > 0.7:
            rule_key = "threat_far_high_conf"
        elif threat_confidence > 0.3:
            rule_key = "threat_far_low_conf"
        else:
            rule_key = "no_threat"

        rule = self.TACTICAL_RULES.get(rule_key)
        if rule is None:
            return None

        action = str(rule["action"])
        if action not in actions:
            action = "hold" if "hold" in actions else actions[0]
        confidence = min(self._sanitize_confidence(float(rule["confidence"])), self.config.heuristic_confidence_cap)

        return OfflineDecision(
            action=action,
            confidence=confidence,
            method="rule_based",
            connectivity_state=self._connectivity,
            rationale_en=f"Rule '{rule_key}' selected '{action}' for tactical safety.",
            rationale_ar=f"Rule '{rule_key}' selected '{action}' for tactical safety.",
        )

    def _heuristic_decision(self, observation: Dict[str, Any], actions: List[str]) -> OfflineDecision:
        """Fallback heuristic when model/rule paths are unavailable."""
        threat_confidence = self._safe_float(observation.get("threat_confidence", 0.0), default=0.0)
        fuel_level = self._safe_float(observation.get("fuel_pct", 100.0), default=100.0)
        if fuel_level < 20.0 and "rtb" in actions:
            action = "rtb"
        elif threat_confidence > 0.6 and "evade" in actions:
            action = "evade"
        elif threat_confidence > 0.3 and "recon" in actions:
            action = "recon"
        else:
            action = "hold" if "hold" in actions else actions[0]

        confidence = min(self.config.heuristic_confidence_cap, 0.4 + 0.4 * threat_confidence)
        return OfflineDecision(
            action=action,
            confidence=confidence,
            method="heuristic",
            connectivity_state=self._connectivity,
            rationale_en=f"Heuristic fallback selected '{action}' for mission continuity.",
            rationale_ar=f"Heuristic fallback selected '{action}' for mission continuity.",
        )

    def _enqueue(self, decision: OfflineDecision) -> None:
        with self._lock:
            self._decision_queue.append(decision)
            if self._connectivity != ConnectivityState.FULL:
                self._pending_sync.append(decision)

    def get_pending_sync(self) -> List[OfflineDecision]:
        """Return the next sync batch and remove it from pending queue."""
        with self._lock:
            batch = self._pending_sync[: self.config.sync_batch_size]
            self._pending_sync = self._pending_sync[self.config.sync_batch_size :]
            return batch

    def mark_synced(self, decision_ids: List[str]) -> int:
        """Mark decisions as synced and return count updated."""
        with self._lock:
            id_set = set(decision_ids)
            count = 0
            for decision in self._decision_queue:
                if decision.decision_id in id_set:
                    decision.synced = True
                    count += 1
            return count

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "connectivity": self._connectivity.value,
                "queue_size": len(self._decision_queue),
                "pending_sync": len(self._pending_sync),
                "offline_since": self._offline_since,
                "has_cached_model": self._cached_model is not None,
            }

    @staticmethod
    def _sanitize_confidence(value: float) -> float:
        if not math.isfinite(value):
            return 0.0
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _safe_float(value: Any, default: float) -> float:
        try:
            cast = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(cast):
            return default
        return cast
