"""Threshold-based platform health and fault monitoring for S3M-Core.

UNCLASSIFIED - CLOSED-RANGE TRAINING USE ONLY
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .messages import FaultEvent, FaultSeverity, HealthState, PlatformState


class HealthMonitor:
    """Evaluates platform telemetry and emits typed fault events."""

    DEFAULT_THRESHOLDS: Dict[str, float] = {
        "cpu_temp_warn_c": 80.0,
        "cpu_temp_critical_c": 90.0,
        "gpu_temp_warn_c": 82.0,
        "gpu_temp_critical_c": 92.0,
        "memory_warn_pct": 85.0,
        "memory_critical_pct": 95.0,
        "disk_warn_pct": 90.0,
        "disk_critical_pct": 97.0,
        "power_voltage_warn_v": 22.0,
        "power_voltage_critical_v": 20.0,
        "fuel_warn_pct": 25.0,
        "fuel_critical_pct": 10.0,
        "battery_warn_pct": 30.0,
        "battery_critical_pct": 15.0,
    }

    def __init__(self, thresholds: Optional[Dict[str, float]] = None) -> None:
        self._default_thresholds: Dict[str, float] = dict(self.DEFAULT_THRESHOLDS)
        if thresholds:
            self._default_thresholds.update(self._coerce_thresholds(thresholds))
        self._platform_thresholds: Dict[str, Dict[str, float]] = {}

    def register_platform(
        self, platform_id: str, thresholds: Optional[Dict[str, float]] = None
    ) -> None:
        """Register an optional threshold override set for one platform."""
        if not isinstance(platform_id, str) or not platform_id.strip():
            raise ValueError("platform_id must be a non-empty string")
        merged = dict(self._default_thresholds)
        if thresholds:
            merged.update(self._coerce_thresholds(thresholds))
        self._platform_thresholds[platform_id] = merged

    def check_health(self, state: PlatformState) -> HealthState:
        """Return a new HealthState that includes detected threshold faults."""
        faults = self.detect_faults(state)
        return HealthState(
            cpu_temp_c=state.health.cpu_temp_c,
            gpu_temp_c=state.health.gpu_temp_c,
            memory_pct=state.health.memory_pct,
            disk_pct=state.health.disk_pct,
            power_voltage=state.health.power_voltage,
            operating_mode=state.health.operating_mode,
            faults=[*state.health.faults, *faults],
        )

    def detect_faults(self, state: PlatformState) -> List[FaultEvent]:
        """Detect platform-level and telemetry-level faults from a platform snapshot."""
        if not isinstance(state, PlatformState):
            raise TypeError("state must be a PlatformState")
        thresholds = self._thresholds_for(state.platform_id)
        faults = self.detect_faults_from_health(state.health, state.platform_id)

        self._append_low_threshold_fault(
            faults=faults,
            source="fuel",
            description="Fuel reserve low",
            value=state.fuel_pct,
            warn_threshold=thresholds["fuel_warn_pct"],
            critical_threshold=thresholds["fuel_critical_pct"],
            units="%",
        )
        self._append_low_threshold_fault(
            faults=faults,
            source="battery",
            description="Battery reserve low",
            value=state.battery_pct,
            warn_threshold=thresholds["battery_warn_pct"],
            critical_threshold=thresholds["battery_critical_pct"],
            units="%",
        )

        comms = (state.comms_status or "").strip().lower()
        # Tactical note: comms degradation can remove human override and C2 coordination.
        if comms in {"offline", "lost", "disconnected"}:
            faults.append(
                FaultEvent(
                    severity=FaultSeverity.CRITICAL,
                    source="comms",
                    description=f"Communications link unavailable ({state.comms_status})",
                )
            )
        elif comms in {"degraded", "intermittent", "jammed", "denied"}:
            faults.append(
                FaultEvent(
                    severity=FaultSeverity.WARNING,
                    source="comms",
                    description=f"Communications link degraded ({state.comms_status})",
                )
            )

        return faults

    def detect_faults_from_health(
        self, health: HealthState, platform_id: str = "unknown"
    ) -> List[FaultEvent]:
        """Detect threshold faults from HealthState metrics only."""
        if not isinstance(health, HealthState):
            raise TypeError("health must be a HealthState")
        thresholds = self._thresholds_for(platform_id)
        faults: List[FaultEvent] = []

        self._append_high_threshold_fault(
            faults=faults,
            source="cpu",
            description="CPU temperature elevated",
            value=health.cpu_temp_c,
            warn_threshold=thresholds["cpu_temp_warn_c"],
            critical_threshold=thresholds["cpu_temp_critical_c"],
            units="C",
        )
        self._append_high_threshold_fault(
            faults=faults,
            source="gpu",
            description="GPU temperature elevated",
            value=health.gpu_temp_c,
            warn_threshold=thresholds["gpu_temp_warn_c"],
            critical_threshold=thresholds["gpu_temp_critical_c"],
            units="C",
        )
        self._append_high_threshold_fault(
            faults=faults,
            source="memory",
            description="Memory pressure high",
            value=health.memory_pct,
            warn_threshold=thresholds["memory_warn_pct"],
            critical_threshold=thresholds["memory_critical_pct"],
            units="%",
        )
        self._append_high_threshold_fault(
            faults=faults,
            source="disk",
            description="Disk utilization high",
            value=health.disk_pct,
            warn_threshold=thresholds["disk_warn_pct"],
            critical_threshold=thresholds["disk_critical_pct"],
            units="%",
        )
        self._append_low_threshold_fault(
            faults=faults,
            source="power",
            description="Input voltage below expected range",
            value=health.power_voltage,
            warn_threshold=thresholds["power_voltage_warn_v"],
            critical_threshold=thresholds["power_voltage_critical_v"],
            units="V",
        )

        return faults

    def _thresholds_for(self, platform_id: str) -> Dict[str, float]:
        if platform_id in self._platform_thresholds:
            return self._platform_thresholds[platform_id]
        return self._default_thresholds

    @staticmethod
    def _coerce_thresholds(thresholds: Dict[str, float]) -> Dict[str, float]:
        coerced: Dict[str, float] = {}
        for key, value in thresholds.items():
            if not isinstance(key, str):
                raise TypeError("threshold keys must be strings")
            coerced[key] = float(value)
        return coerced

    @staticmethod
    def _append_high_threshold_fault(
        *,
        faults: List[FaultEvent],
        source: str,
        description: str,
        value: float,
        warn_threshold: float,
        critical_threshold: float,
        units: str,
    ) -> None:
        if value >= critical_threshold:
            faults.append(
                FaultEvent(
                    severity=FaultSeverity.CRITICAL,
                    source=source,
                    description=(
                        f"{description}: {value:.2f}{units} (critical >= {critical_threshold:.2f}{units})"
                    ),
                )
            )
        elif value >= warn_threshold:
            faults.append(
                FaultEvent(
                    severity=FaultSeverity.WARNING,
                    source=source,
                    description=(
                        f"{description}: {value:.2f}{units} (warning >= {warn_threshold:.2f}{units})"
                    ),
                )
            )

    @staticmethod
    def _append_low_threshold_fault(
        *,
        faults: List[FaultEvent],
        source: str,
        description: str,
        value: float,
        warn_threshold: float,
        critical_threshold: float,
        units: str,
    ) -> None:
        if value <= critical_threshold:
            faults.append(
                FaultEvent(
                    severity=FaultSeverity.CRITICAL,
                    source=source,
                    description=(
                        f"{description}: {value:.2f}{units} (critical <= {critical_threshold:.2f}{units})"
                    ),
                )
            )
        elif value <= warn_threshold:
            faults.append(
                FaultEvent(
                    severity=FaultSeverity.WARNING,
                    source=source,
                    description=(
                        f"{description}: {value:.2f}{units} (warning <= {warn_threshold:.2f}{units})"
                    ),
                )
            )
