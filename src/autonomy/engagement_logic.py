"""HOOL/HOTL/HITL engagement logic for tactical autonomy.

This module implements a full detect->classify->recommend->authorize->execute
pipeline that can run fully offline on edge compute. The pipeline enforces
ROE/IFF safeguards before any payload action is emitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Protocol, Sequence, Tuple


class AuthorizationMode(str, Enum):
    """Command authority mode for autonomous engagement."""

    HITL = "hitl"  # Human-in-the-loop: explicit approval required.
    HOTL = "hotl"  # Human-on-the-loop: autonomous unless operator veto.
    HOOL = "hool"  # Human-out-of-the-loop: strict auto-authorization gates.


class PayloadAdapterProtocol(Protocol):
    """Minimal payload interface used by the engagement pipeline."""

    def operator_authorized_action(self, action: Mapping[str, Any]) -> Any:
        """Execute a payload action approved by command authority."""


class _NullPayloadAdapter:
    """Fallback adapter for simulation-only runs without a payload backend."""

    def operator_authorized_action(self, action: Mapping[str, Any]) -> Dict[str, Any]:
        return {"status": "simulated", "action": dict(action)}


@dataclass
class ThreatTrack:
    """Normalized threat track used by tactical engagement scoring."""

    track_id: str
    position: Tuple[float, float, float]
    velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    confidence: float = 0.0
    priority: float = 1.0
    classification: str = "unknown"
    iff_status: str = "unknown"
    zone_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.track_id:
            raise ValueError("track_id is required")
        if len(self.position) != 3:
            raise ValueError("position must be 3D")
        if len(self.velocity) != 3:
            raise ValueError("velocity must be 3D")
        self.position = tuple(float(v) for v in self.position)
        self.velocity = tuple(float(v) for v in self.velocity)
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.priority = max(0.0, float(self.priority))
        self.classification = str(self.classification or "unknown").lower()
        self.iff_status = str(self.iff_status or "unknown").lower()
        if self.zone_id is not None:
            self.zone_id = str(self.zone_id)


@dataclass
class ThreatScore:
    """Composite threat score and per-factor breakdown."""

    track: ThreatTrack
    composite_score: float
    components: Dict[str, float]


@dataclass
class EngagementRecommendation:
    """Recommended engagement action after threat prioritization."""

    action: str
    confidence: float
    reason: str
    track: Optional[ThreatTrack] = None
    aim_solution: Dict[str, Any] = field(default_factory=dict)
    scoring: Dict[str, float] = field(default_factory=dict)


@dataclass
class EngagementResult:
    """End-to-end engagement pipeline output."""

    mode: AuthorizationMode
    status: str
    recommendation: EngagementRecommendation
    authorization: Dict[str, Any]
    execution: Dict[str, Any]
    prioritized_tracks: List[ThreatScore] = field(default_factory=list)


class ThreatPrioritizer:
    """Composite threat scorer based on tactical urgency and confidence."""

    def __init__(
        self,
        distance_weight: float = 0.35,
        closing_speed_weight: float = 0.25,
        confidence_weight: float = 0.20,
        priority_weight: float = 0.20,
        max_range_m: float = 5_000.0,
        max_closing_speed_mps: float = 300.0,
    ) -> None:
        weights = [distance_weight, closing_speed_weight, confidence_weight, priority_weight]
        if any(w < 0.0 for w in weights):
            raise ValueError("weights must be non-negative")
        total = float(sum(weights))
        if total <= 0:
            raise ValueError("sum of weights must be > 0")
        self.distance_weight = float(distance_weight) / total
        self.closing_speed_weight = float(closing_speed_weight) / total
        self.confidence_weight = float(confidence_weight) / total
        self.priority_weight = float(priority_weight) / total
        self.max_range_m = max(1.0, float(max_range_m))
        self.max_closing_speed_mps = max(1.0, float(max_closing_speed_mps))

    def evaluate_threats(
        self,
        threats: Sequence[ThreatTrack | Mapping[str, Any]],
        ownship_position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> List[ThreatScore]:
        """Score and sort threats from highest to lowest urgency."""
        scores: List[ThreatScore] = []
        ownship = tuple(float(v) for v in ownship_position)
        for item in threats:
            track = item if isinstance(item, ThreatTrack) else _coerce_threat_track(item)
            distance = float(math.dist(track.position, ownship))
            closing_speed = self._compute_closing_speed(track=track, ownship_position=ownship)
            distance_component = self._normalize_distance(distance)
            closing_component = self._normalize_closing_speed(closing_speed)
            confidence_component = max(0.0, min(1.0, track.confidence))
            priority_component = max(0.0, min(1.0, track.priority / 10.0))

            composite = (
                self.distance_weight * distance_component
                + self.closing_speed_weight * closing_component
                + self.confidence_weight * confidence_component
                + self.priority_weight * priority_component
            )
            scores.append(
                ThreatScore(
                    track=track,
                    composite_score=max(0.0, min(1.0, composite)),
                    components={
                        "distance": distance_component,
                        "closing_speed": closing_component,
                        "confidence": confidence_component,
                        "priority": priority_component,
                    },
                )
            )
        scores.sort(key=lambda s: (s.composite_score, s.track.confidence, s.track.priority), reverse=True)
        return scores

    def _normalize_distance(self, distance_m: float) -> float:
        """Convert distance to urgency where closer threats score higher."""
        ratio = min(1.0, max(0.0, float(distance_m) / self.max_range_m))
        return 1.0 - ratio

    def _normalize_closing_speed(self, closing_speed_mps: float) -> float:
        """Convert closing speed to urgency where faster closure scores higher."""
        value = max(0.0, float(closing_speed_mps))
        return min(1.0, value / self.max_closing_speed_mps)

    @staticmethod
    def _compute_closing_speed(track: ThreatTrack, ownship_position: Tuple[float, float, float]) -> float:
        """Positive when the track is moving toward ownship along LOS."""
        los = (
            ownship_position[0] - track.position[0],
            ownship_position[1] - track.position[1],
            ownship_position[2] - track.position[2],
        )
        dist = math.sqrt(los[0] ** 2 + los[1] ** 2 + los[2] ** 2)
        if dist <= 1e-6:
            return 0.0
        unit_los = (los[0] / dist, los[1] / dist, los[2] / dist)
        return (
            track.velocity[0] * unit_los[0]
            + track.velocity[1] * unit_los[1]
            + track.velocity[2] * unit_los[2]
        )


class EngagementPipeline:
    """End-to-end tactical engagement logic with authorization control."""

    def __init__(
        self,
        payload_adapter: Optional[PayloadAdapterProtocol] = None,
        authorization_mode: AuthorizationMode = AuthorizationMode.HITL,
        prioritizer: Optional[ThreatPrioritizer] = None,
        recommendation_threshold: float = 0.60,
    ) -> None:
        self.payload_adapter: PayloadAdapterProtocol = payload_adapter or _NullPayloadAdapter()
        self.authorization_mode = AuthorizationMode(authorization_mode)
        self.prioritizer = prioritizer or ThreatPrioritizer()
        self.recommendation_threshold = max(0.0, min(1.0, float(recommendation_threshold)))

    def run_cycle(
        self,
        detections: Sequence[Mapping[str, Any]],
        context: Optional[MutableMapping[str, Any]] = None,
    ) -> EngagementResult:
        """Execute detect->classify->recommend->authorize->execute pipeline."""
        ctx: MutableMapping[str, Any] = context if isinstance(context, MutableMapping) else {}
        tracks = self._detect(detections)
        classified = self._classify(tracks, ctx)
        ownship = _as_xyz(ctx.get("ownship_position", (0.0, 0.0, 0.0)))
        prioritized = self.prioritizer.evaluate_threats(classified, ownship_position=ownship)
        recommendation = self._recommend(prioritized, ctx)
        authorization = self._authorize(recommendation, ctx)
        execution = self._execute(recommendation, authorization, ctx)
        status = str(execution.get("status", "completed"))
        return EngagementResult(
            mode=self.authorization_mode,
            status=status,
            recommendation=recommendation,
            authorization=authorization,
            execution=execution,
            prioritized_tracks=prioritized,
        )

    def process_hool_engagement(
        self, recommendation: EngagementRecommendation, context: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Apply strict HOOL auto-authorization gates before payload use."""
        track = recommendation.track
        confidence_gate = recommendation.confidence >= 0.95
        roe_ok = self._check_roe(recommendation, context)
        zone_ok = bool(track and self._check_zone_authorized(track, context))
        iff_ok = bool(track and self._check_iff(track, context))
        mission_token_ok = self._check_mission_token(context)
        authorized = bool(
            recommendation.action == "engage"
            and track is not None
            and confidence_gate
            and roe_ok
            and zone_ok
            and iff_ok
            and mission_token_ok
        )
        return {
            "mode": AuthorizationMode.HOOL.value,
            "authorized": authorized,
            "reason": "hool_gate_pass" if authorized else "hool_gate_failed",
            "checks": {
                "confidence": confidence_gate,
                "roe": roe_ok,
                "zone_authorized": zone_ok,
                "iff_clear": iff_ok,
                "mission_token": mission_token_ok,
            },
        }

    def process_hotl_engagement(
        self, recommendation: EngagementRecommendation, context: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Process HOTL policy: autonomous unless safety fails or operator vetoes."""
        track = recommendation.track
        if track is None or recommendation.action != "engage":
            return {"mode": AuthorizationMode.HOTL.value, "authorized": False, "reason": "no_engagement_target"}
        if bool(context.get("operator_veto", False)):
            return {"mode": AuthorizationMode.HOTL.value, "authorized": False, "reason": "operator_veto"}
        roe_ok = self._check_roe(recommendation, context)
        iff_ok = self._check_iff(track, context)
        zone_ok = self._check_zone_authorized(track, context)
        if not (roe_ok and iff_ok and zone_ok):
            return {
                "mode": AuthorizationMode.HOTL.value,
                "authorized": False,
                "reason": "safety_gate_failed",
                "checks": {"roe": roe_ok, "iff_clear": iff_ok, "zone_authorized": zone_ok},
            }
        return {"mode": AuthorizationMode.HOTL.value, "authorized": True, "reason": "hotl_auto_authorized"}

    def _process_hitl_engagement(
        self, recommendation: EngagementRecommendation, context: Mapping[str, Any]
    ) -> Dict[str, Any]:
        """Process HITL policy: requires explicit operator approval."""
        track = recommendation.track
        if track is None or recommendation.action != "engage":
            return {"mode": AuthorizationMode.HITL.value, "authorized": False, "reason": "no_engagement_target"}
        operator_ok = bool(context.get("operator_authorized", False))
        roe_ok = self._check_roe(recommendation, context)
        iff_ok = self._check_iff(track, context)
        zone_ok = self._check_zone_authorized(track, context)
        authorized = bool(operator_ok and roe_ok and iff_ok and zone_ok)
        return {
            "mode": AuthorizationMode.HITL.value,
            "authorized": authorized,
            "reason": "hitl_authorized" if authorized else "operator_or_safety_gate_failed",
            "checks": {
                "operator_authorized": operator_ok,
                "roe": roe_ok,
                "iff_clear": iff_ok,
                "zone_authorized": zone_ok,
            },
        }

    def _detect(self, detections: Sequence[Mapping[str, Any]]) -> List[ThreatTrack]:
        tracks: List[ThreatTrack] = []
        for raw in detections:
            try:
                tracks.append(_coerce_threat_track(raw))
            except Exception:
                # Tactical context: malformed tracks are ignored to avoid invalid
                # autonomous engagement decisions in degraded sensor conditions.
                continue
        return tracks

    def _classify(self, tracks: Sequence[ThreatTrack], context: Mapping[str, Any]) -> List[ThreatTrack]:
        hostile_threshold = max(0.0, min(1.0, float(context.get("hostile_threshold", 0.70))))
        classified: List[ThreatTrack] = []
        for track in tracks:
            cls = track.classification
            if cls not in {"hostile", "friendly", "neutral"}:
                cls = "hostile" if track.confidence >= hostile_threshold else "unknown"
            classified.append(
                ThreatTrack(
                    track_id=track.track_id,
                    position=track.position,
                    velocity=track.velocity,
                    confidence=track.confidence,
                    priority=track.priority,
                    classification=cls,
                    iff_status=track.iff_status,
                    zone_id=track.zone_id,
                    metadata=dict(track.metadata),
                )
            )
        return classified

    def _recommend(
        self, prioritized: Sequence[ThreatScore], context: Mapping[str, Any]
    ) -> EngagementRecommendation:
        if not prioritized:
            return EngagementRecommendation(
                action="hold_fire",
                confidence=1.0,
                reason="no_detected_threats",
            )
        top = prioritized[0]
        if top.track.classification == "friendly":
            return EngagementRecommendation(
                action="hold_fire",
                confidence=1.0,
                reason="friendly_track_detected",
                track=top.track,
                scoring=top.components,
            )
        composite = top.composite_score
        confidence = max(0.0, min(1.0, 0.5 * composite + 0.5 * top.track.confidence))
        if composite < self.recommendation_threshold:
            return EngagementRecommendation(
                action="hold_fire",
                confidence=confidence,
                reason="below_engagement_threshold",
                track=top.track,
                scoring=top.components,
            )
        aim = self._compute_aim_solution(top.track, context)
        return EngagementRecommendation(
            action="engage",
            confidence=confidence,
            reason="highest_priority_hostile_track",
            track=top.track,
            aim_solution=aim,
            scoring=top.components,
        )

    def _authorize(
        self, recommendation: EngagementRecommendation, context: Mapping[str, Any]
    ) -> Dict[str, Any]:
        if recommendation.action != "engage":
            return {"mode": self.authorization_mode.value, "authorized": True, "reason": "defensive_hold_action"}
        if self.authorization_mode == AuthorizationMode.HOOL:
            return self.process_hool_engagement(recommendation, context)
        if self.authorization_mode == AuthorizationMode.HOTL:
            return self.process_hotl_engagement(recommendation, context)
        return self._process_hitl_engagement(recommendation, context)

    def _execute(
        self,
        recommendation: EngagementRecommendation,
        authorization: Mapping[str, Any],
        context: Mapping[str, Any],
    ) -> Dict[str, Any]:
        track = recommendation.track
        authorized = bool(authorization.get("authorized", False))
        commanded_action = recommendation.action if authorized else "hold_fire"
        action_payload = {
            "action": commanded_action,
            "mode": self.authorization_mode.value,
            "reason": recommendation.reason,
            "authorization": dict(authorization),
            "mission_id": context.get("mission_id"),
            "target_track_id": track.track_id if track else None,
            "aim_solution": dict(recommendation.aim_solution),
            "confidence": recommendation.confidence,
        }
        try:
            # Every payload operation is routed through operator_authorized_action.
            adapter_response = self.payload_adapter.operator_authorized_action(action_payload)
            return {
                "status": "executed",
                "commanded_action": commanded_action,
                "adapter_response": adapter_response,
            }
        except Exception as exc:
            return {
                "status": "error",
                "commanded_action": commanded_action,
                "error": str(exc),
            }

    def _check_roe(self, recommendation: EngagementRecommendation, context: Mapping[str, Any]) -> bool:
        """Evaluate ROE constraints for the proposed action."""
        if recommendation.action != "engage":
            return True
        roe = str(context.get("roe_state", context.get("rules_of_engagement", "weapons_tight"))).lower()
        if roe == "weapons_hold":
            return False
        if roe == "weapons_free":
            return bool(context.get("roe_allow_engagement", True))
        # weapons_tight and unknown policies default to strict behavior.
        cls_ok = recommendation.track is not None and recommendation.track.classification == "hostile"
        conf_ok = recommendation.confidence >= float(context.get("roe_confidence_min", 0.80))
        return bool(cls_ok and conf_ok and context.get("roe_allow_engagement", True))

    def _check_iff(self, track: ThreatTrack, context: Mapping[str, Any]) -> bool:
        """IFF gate to prevent friendly fire under uncertain classification."""
        iff = str(track.iff_status).lower()
        if iff in {"friendly", "ally"}:
            return False
        if iff in {"hostile", "bogey", "clear"}:
            return True
        if iff == "neutral":
            return bool(context.get("allow_neutral_engagement", False))
        return bool(context.get("allow_unknown_iff", False))

    def _check_zone_authorized(self, track: ThreatTrack, context: Mapping[str, Any]) -> bool:
        zones = context.get("authorized_zones")
        if zones is None:
            return True
        if track.zone_id is None:
            return bool(context.get("allow_unzoned_target", False))
        if isinstance(zones, (list, tuple, set)):
            return str(track.zone_id) in {str(z) for z in zones}
        return str(track.zone_id) == str(zones)

    @staticmethod
    def _check_mission_token(context: Mapping[str, Any]) -> bool:
        token = context.get("active_mission_token", context.get("mission_token"))
        if isinstance(token, Mapping):
            return bool(token.get("active", False) and not bool(token.get("expired", False)))
        if isinstance(token, str):
            return bool(token.strip()) and bool(context.get("mission_token_active", True))
        if isinstance(token, bool):
            return token
        return False

    def _compute_aim_solution(self, track: ThreatTrack, context: Mapping[str, Any]) -> Dict[str, Any]:
        """Compute a lead/intercept aim point for moving targets."""
        ownship = _as_xyz(context.get("ownship_position", (0.0, 0.0, 0.0)))
        muzzle_speed = max(1.0, float(context.get("weapon_speed_mps", 750.0)))
        rx = track.position[0] - ownship[0]
        ry = track.position[1] - ownship[1]
        rz = track.position[2] - ownship[2]
        vx, vy, vz = track.velocity

        a = vx * vx + vy * vy + vz * vz - muzzle_speed * muzzle_speed
        b = 2.0 * (rx * vx + ry * vy + rz * vz)
        c = rx * rx + ry * ry + rz * rz

        t_impact: Optional[float] = None
        if abs(a) < 1e-9:
            if abs(b) > 1e-9:
                t = -c / b
                if t > 0:
                    t_impact = t
        else:
            disc = b * b - 4.0 * a * c
            if disc >= 0.0:
                sqrt_disc = math.sqrt(disc)
                t1 = (-b - sqrt_disc) / (2.0 * a)
                t2 = (-b + sqrt_disc) / (2.0 * a)
                candidates = [t for t in (t1, t2) if t > 0.0]
                if candidates:
                    t_impact = min(candidates)

        if t_impact is None:
            return {
                "valid": False,
                "solution_type": "no_intercept_solution",
                "aim_point": list(track.position),
                "time_to_impact_s": None,
                "distance_m": float(math.dist(ownship, track.position)),
            }

        aim_point = (
            track.position[0] + track.velocity[0] * t_impact,
            track.position[1] + track.velocity[1] * t_impact,
            track.position[2] + track.velocity[2] * t_impact,
        )
        return {
            "valid": True,
            "solution_type": "lead_intercept",
            "aim_point": [float(v) for v in aim_point],
            "time_to_impact_s": float(t_impact),
            "distance_m": float(math.dist(ownship, aim_point)),
            "lead_vector_m": [float(aim_point[i] - track.position[i]) for i in range(3)],
        }


def _as_xyz(value: Any) -> Tuple[float, float, float]:
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return (float(value[0]), float(value[1]), float(value[2]))
    return (0.0, 0.0, 0.0)


def _coerce_threat_track(raw: Mapping[str, Any]) -> ThreatTrack:
    if not isinstance(raw, Mapping):
        raise ValueError("threat must be a mapping")
    track_id = str(raw.get("track_id") or raw.get("id") or "").strip()
    if not track_id:
        raise ValueError("track_id is required")
    return ThreatTrack(
        track_id=track_id,
        position=_as_xyz(raw.get("position", (0.0, 0.0, 0.0))),
        velocity=_as_xyz(raw.get("velocity", (0.0, 0.0, 0.0))),
        confidence=float(raw.get("confidence", 0.0)),
        priority=float(raw.get("priority", 1.0)),
        classification=str(raw.get("classification", "unknown")),
        iff_status=str(raw.get("iff_status", raw.get("iff", "unknown"))),
        zone_id=raw.get("zone_id"),
        metadata=dict(raw.get("metadata", {})) if isinstance(raw.get("metadata", {}), Mapping) else {},
    )


__all__ = [
    "AuthorizationMode",
    "ThreatTrack",
    "ThreatScore",
    "EngagementRecommendation",
    "EngagementResult",
    "ThreatPrioritizer",
    "EngagementPipeline",
]
