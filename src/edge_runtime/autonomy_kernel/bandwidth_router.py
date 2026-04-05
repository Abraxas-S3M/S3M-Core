"""
S3M Bandwidth-Aware Model Switching Router
==========================================
Monitors link conditions and selects the safest model tier for
mission continuity under contested or denied connectivity.
"""

from __future__ import annotations

import math
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List

from pydantic import BaseModel, Field


class BandwidthTier(str, Enum):
    FULL = "full"  # >10 Mbps
    MEDIUM = "medium"  # 1-10 Mbps
    LOW = "low"  # 0.1-1 Mbps
    ZERO = "zero"  # No connectivity


class BandwidthState(BaseModel):
    """Current link quality measurement."""

    measured_mbps: float = 0.0
    tier: BandwidthTier = BandwidthTier.ZERO
    latency_ms: float = 999.0
    packet_loss_pct: float = 100.0
    last_measured: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    stable: bool = False


class ModelSwitchDecision(BaseModel):
    """Decision to switch inference model tier."""

    from_model: str = ""
    to_model: str = ""
    reason: str = ""
    bandwidth_tier: BandwidthTier = BandwidthTier.ZERO
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BandwidthRouter:
    """
    Routes inference to a model compatible with current bandwidth tier.

    The tactical goal is to preserve decision authority at the edge:
    high tiers use richer models; zero tier falls back to rule-based logic.
    """

    TIER_THRESHOLDS: Dict[BandwidthTier, float] = {
        BandwidthTier.FULL: 10.0,
        BandwidthTier.MEDIUM: 1.0,
        BandwidthTier.LOW: 0.1,
        BandwidthTier.ZERO: 0.0,
    }

    MODEL_MAP: Dict[BandwidthTier, str] = {
        BandwidthTier.FULL: "mistral-7b-q4",
        BandwidthTier.MEDIUM: "phi3-mini-q4",
        BandwidthTier.LOW: "distilled-1b-q8",
        BandwidthTier.ZERO: "rule_based_fallback",
    }

    def __init__(self, hysteresis_mbps: float = 0.5) -> None:
        if hysteresis_mbps < 0:
            raise ValueError("hysteresis_mbps must be non-negative")
        self._hysteresis = float(hysteresis_mbps)
        self._current_tier = BandwidthTier.ZERO
        self._current_model = self.MODEL_MAP[BandwidthTier.ZERO]
        self._history: List[ModelSwitchDecision] = []
        self._lock = threading.Lock()

    def update_bandwidth(
        self,
        measured_mbps: float,
        latency_ms: float = 50.0,
        packet_loss_pct: float = 0.0,
    ) -> BandwidthState:
        """Update bandwidth measurement and switch model tier if required."""
        measured = self._sanitize_non_negative(measured_mbps, fallback=0.0)
        latency = self._sanitize_non_negative(latency_ms, fallback=999.0)
        packet_loss = self._sanitize_non_negative(packet_loss_pct, fallback=100.0)
        packet_loss = min(100.0, packet_loss)

        with self._lock:
            new_tier = self._classify_tier(measured)
            is_stable = new_tier == self._current_tier

            if new_tier != self._current_tier:
                old_model = self._current_model
                new_model = self.MODEL_MAP[new_tier]
                self._current_tier = new_tier
                self._current_model = new_model

                switch = ModelSwitchDecision(
                    from_model=old_model,
                    to_model=new_model,
                    reason=f"Bandwidth changed to {measured:.1f} Mbps -> tier {new_tier.value}",
                    bandwidth_tier=new_tier,
                )
                self._history.append(switch)
                if len(self._history) > 500:
                    self._history = self._history[-500:]

            return BandwidthState(
                measured_mbps=measured,
                tier=self._current_tier,
                latency_ms=latency,
                packet_loss_pct=packet_loss,
                stable=is_stable,
            )

    def _classify_tier(self, mbps: float) -> BandwidthTier:
        """Classify bandwidth with hysteresis to prevent oscillation."""
        for tier in (BandwidthTier.FULL, BandwidthTier.MEDIUM, BandwidthTier.LOW):
            threshold = self.TIER_THRESHOLDS[tier]
            if self._current_tier == tier:
                if mbps >= threshold - self._hysteresis:
                    return tier
            elif mbps >= threshold:
                return tier
        return BandwidthTier.ZERO

    def get_current_model(self) -> str:
        with self._lock:
            return self._current_model

    def get_current_tier(self) -> BandwidthTier:
        with self._lock:
            return self._current_tier

    def get_switch_history(self) -> List[ModelSwitchDecision]:
        with self._lock:
            return list(self._history)

    @staticmethod
    def _sanitize_non_negative(value: float, fallback: float) -> float:
        try:
            cast = float(value)
        except (TypeError, ValueError):
            return fallback
        if not math.isfinite(cast):
            return fallback
        return max(0.0, cast)
