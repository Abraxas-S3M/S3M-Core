"""Envelope checker for human-out-of-loop tactical missions.

Military context:
Every autonomous action is screened against commander-approved mission bounds
before execution to prevent unauthorized escalation in denied environments.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from services.autonomy.hool_extension.models import EnvelopeViolation, HOOLMissionState, MissionEnvelope


class EnvelopeChecker:
    """Validate mission state against all envelope dimensions."""

    def __init__(self, envelope: MissionEnvelope):
        self.envelope = envelope

    @staticmethod
    def _point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
        x, y = point
        inside = False
        n = len(polygon)
        if n < 3:
            return False
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            intersects = (yi > y) != (yj > y) and x < ((xj - xi) * (y - yi) / ((yj - yi) + 1e-9) + xi)
            if intersects:
                inside = not inside
            j = i
        return inside

    def check_all(self, state: HOOLMissionState) -> tuple[bool, List[EnvelopeViolation]]:
        """Run all envelope checks and return pass/fail with violation list."""
        violations: List[EnvelopeViolation] = []
        checks = [
            self.check_geofence(state.current_position),
            self.check_temporal(datetime.now(timezone.utc)),
            self.check_energy(state.battery_pct, state.fuel_pct),
            self.check_comms(self._seconds_since_contact(state.comms_status)),
            self.check_risk(state.risk_score),
            self.check_escalation(state.proposed_escalation_level),
            self.check_targets(state.targets_engaged),
            self.check_roe(state.proposed_action, state.target_type or ""),
        ]
        for item in checks:
            if item is not None:
                violations.append(item)
        all_pass = all(v.severity == "warning" for v in violations) if violations else True
        return all_pass, violations

    def _seconds_since_contact(self, comms_status: object) -> float:
        if isinstance(comms_status, dict):
            return float(comms_status.get("seconds_since_last_contact", 0.0))
        if isinstance(comms_status, (int, float)):
            return float(comms_status)
        if isinstance(comms_status, str):
            status = comms_status.lower()
            if status == "lost":
                return self.envelope.max_comms_loss_seconds + 1.0
            return 0.0
        return 0.0

    def check_geofence(self, position: tuple) -> Optional[EnvelopeViolation]:
        """Check 3D geofence with 2D polygon containment and altitude limits."""
        lat, lon, alt = float(position[0]), float(position[1]), float(position[2])
        polygon = [(v[0], v[1]) for v in self.envelope.geofence_vertices]
        inside_2d = self._point_in_polygon((lat, lon), polygon)
        altitude_ok = self.envelope.geofence_floor_m <= alt <= self.envelope.geofence_ceiling_m
        if inside_2d and altitude_ok:
            return None
        return EnvelopeViolation(
            dimension="geofence",
            current_value={"position": position},
            limit_value={
                "floor": self.envelope.geofence_floor_m,
                "ceiling": self.envelope.geofence_ceiling_m,
                "polygon": polygon,
            },
            severity="critical",
            recoverable=True,
            recommended_action="RTB to nearest geofence point",
        )

    def check_temporal(self, current_time: datetime) -> Optional[EnvelopeViolation]:
        """Enforce mission time-window and trigger RTB planning near deadline."""
        start_dt, end_dt = self.envelope.time_window
        if current_time > end_dt:
            return EnvelopeViolation(
                dimension="temporal",
                current_value=current_time.isoformat(),
                limit_value=end_dt.isoformat(),
                severity="critical",
                recoverable=False,
                recommended_action="IMMEDIATE RTB",
            )
        duration = max((end_dt - start_dt).total_seconds(), 1.0)
        remaining = max((end_dt - current_time).total_seconds(), 0.0)
        if remaining / duration < 0.10:
            return EnvelopeViolation(
                dimension="temporal",
                current_value=remaining,
                limit_value="10% remaining threshold",
                severity="warning",
                recoverable=True,
                recommended_action="begin RTB planning",
            )
        return None

    def check_roe(self, proposed_action: str, target_type: str) -> Optional[EnvelopeViolation]:
        """Validate proposed engagement action against current ROE constraints."""
        action = (proposed_action or "").lower()
        target = (target_type or "").upper()
        roe = self.envelope.roe_level
        if "engage" not in action and "strike" not in action:
            return None
        if roe == "weapons_hold":
            return EnvelopeViolation(
                dimension="roe",
                current_value=proposed_action,
                limit_value=roe,
                severity="violation",
                recoverable=True,
                recommended_action="abort engagement",
            )
        if roe == "weapons_tight" and target and target not in {t.upper() for t in self.envelope.allowed_target_types}:
            return EnvelopeViolation(
                dimension="roe",
                current_value=target,
                limit_value=self.envelope.allowed_target_types,
                severity="violation",
                recoverable=True,
                recommended_action="abort engagement",
            )
        return None

    def check_energy(self, battery_pct, fuel_pct) -> Optional[EnvelopeViolation]:
        """Check reserve thresholds and infer whether RTB remains feasible."""
        battery = float(battery_pct)
        fuel = float(fuel_pct)
        below_min = battery < self.envelope.min_battery_pct or fuel < self.envelope.min_fuel_pct
        if not below_min:
            return None
        can_reach_rtb = battery >= max(5.0, self.envelope.min_battery_pct - 5.0) or fuel >= max(
            5.0, self.envelope.min_fuel_pct - 5.0
        )
        severity = "warning" if can_reach_rtb else "critical"
        return EnvelopeViolation(
            dimension="energy",
            current_value={"battery_pct": battery, "fuel_pct": fuel},
            limit_value={"min_battery_pct": self.envelope.min_battery_pct, "min_fuel_pct": self.envelope.min_fuel_pct},
            severity=severity,
            recoverable=can_reach_rtb,
            recommended_action="RTB with energy reserve protection",
        )

    def check_comms(self, seconds_since_last_contact) -> Optional[EnvelopeViolation]:
        """Check lost-link timeout threshold for communications resilience."""
        seconds = float(seconds_since_last_contact)
        if seconds <= self.envelope.max_comms_loss_seconds:
            return None
        return EnvelopeViolation(
            dimension="comms",
            current_value=seconds,
            limit_value=self.envelope.max_comms_loss_seconds,
            severity="critical",
            recoverable=True,
            recommended_action="execute lost-link procedure",
        )

    def check_risk(self, risk_score) -> Optional[EnvelopeViolation]:
        """Check risk score against commander-approved mission risk cap."""
        score = float(risk_score)
        if score <= self.envelope.max_risk_score:
            return None
        return EnvelopeViolation(
            dimension="risk",
            current_value=score,
            limit_value=self.envelope.max_risk_score,
            severity="violation",
            recoverable=True,
            recommended_action="disengage and RTB",
        )

    def check_escalation(self, proposed_level: int) -> Optional[EnvelopeViolation]:
        """Enforce escalation ceiling for autonomous engagement authority."""
        if int(proposed_level) <= self.envelope.max_escalation_level:
            return None
        return EnvelopeViolation(
            dimension="escalation",
            current_value=int(proposed_level),
            limit_value=self.envelope.max_escalation_level,
            severity="violation",
            recoverable=True,
            recommended_action="cannot escalate without human approval",
        )

    def check_targets(self, targets_engaged: int) -> Optional[EnvelopeViolation]:
        """Enforce target engagement quota in mission envelope."""
        if int(targets_engaged) <= self.envelope.max_targets:
            return None
        return EnvelopeViolation(
            dimension="engagement",
            current_value=int(targets_engaged),
            limit_value=self.envelope.max_targets,
            severity="violation",
            recoverable=True,
            recommended_action="no further engagements",
        )
