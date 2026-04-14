"""Predictive defense orchestration manager for trajectory-to-action automation.

Military context:
This manager executes a full predictive kill-web cycle to pre-position
interceptors and cue effectors before threats enter defended zones.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Any, Dict, List, Optional, Protocol, Tuple

from services.predictive_defense.models import (
    DefensePosture,
    PredictiveAlert,
    ThreatTrajectoryPrediction,
)
from services.predictive_defense.preposition_optimizer import (
    InterceptorProfile,
    PrePositionOptimizer,
)
from services.predictive_defense.swarm_analyzer import SwarmAnalyzer
from services.predictive_defense.track_genome_bridge import TrackGenomeBridge
from services.predictive_defense.trajectory_predictor import GenomeAwareTrajectoryPredictor
from src.fusion.threat_genome_correlator import ThreatGenomeCorrelator
from src.threat_genome.genome_store import ThreatGenomeStore


class RadarManagerLike(Protocol):
    def list_tracks(self) -> List[Any]:
        ...


class TargetAllocatorLike(Protocol):
    def allocate(
        self,
        target_id: str,
        target_position: Tuple[float, float, float],
        target_speed_mps: float,
        target_classification: str,
    ) -> Any:
        ...


class InterceptorManagerLike(Protocol):
    def assign_target(self, interceptor_id: str, target_id: str) -> bool:
        ...

    def launch(self, interceptor_id: str) -> bool:
        ...

    def radar_acquired(self, interceptor_id: str) -> bool:
        ...


def _utc_now_s() -> float:
    return datetime.now(timezone.utc).timestamp()


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return _serialize(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


class PredictiveDefenseManager:
    """Run predictive threat trajectory analysis and defensive cueing."""

    def __init__(
        self,
        *,
        radar_manager: Optional[RadarManagerLike] = None,
        target_allocator: Optional[TargetAllocatorLike] = None,
        interceptor_manager: Optional[InterceptorManagerLike] = None,
        defended_asset_position_m: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        defended_asset_name_en: str = "Defended asset",
        defended_asset_name_ar: str = "الأصل المحمي",
        genome_store: Optional[ThreatGenomeStore] = None,
    ) -> None:
        self._lock = RLock()
        self.radar_manager = radar_manager
        self.target_allocator = target_allocator
        self.interceptor_manager = interceptor_manager
        self.defended_asset_position_m = (
            float(defended_asset_position_m[0]),
            float(defended_asset_position_m[1]),
            float(defended_asset_position_m[2]),
        )
        self.defended_asset_name_en = defended_asset_name_en
        self.defended_asset_name_ar = defended_asset_name_ar

        self._store = genome_store or ThreatGenomeStore()
        self.correlator = ThreatGenomeCorrelator(store=self._store)
        self.bridge = TrackGenomeBridge()
        self.trajectory_predictor = GenomeAwareTrajectoryPredictor()
        self.swarm_analyzer = SwarmAnalyzer()
        self.preposition_optimizer = PrePositionOptimizer()

        self._interceptor_profiles: Dict[str, InterceptorProfile] = {}
        self._last_posture: Optional[DefensePosture] = None
        self._genome_context_by_track: Dict[str, Dict[str, Any]] = {}

    def configure_interceptors(self, interceptor_profiles: List[InterceptorProfile]) -> None:
        with self._lock:
            self._interceptor_profiles = {profile.interceptor_id: profile for profile in interceptor_profiles}

    def update_defended_asset(
        self,
        *,
        position_m: Tuple[float, float, float],
        name_en: Optional[str] = None,
        name_ar: Optional[str] = None,
    ) -> None:
        with self._lock:
            self.defended_asset_position_m = (float(position_m[0]), float(position_m[1]), float(position_m[2]))
            if name_en:
                self.defended_asset_name_en = str(name_en)
            if name_ar:
                self.defended_asset_name_ar = str(name_ar)

    def process_cycle(self, tracks: Optional[List[Any]] = None, *, now_s: Optional[float] = None) -> DefensePosture:
        """Execute one full predictive-defense cycle and return posture output."""
        with self._lock:
            current_time_s = float(now_s) if now_s is not None else _utc_now_s()
            active_tracks = tracks if tracks is not None else self._collect_tracks()
            contexts = self.bridge.to_contexts(active_tracks)
            trajectory_predictions: List[ThreatTrajectoryPrediction] = []
            for context in contexts:
                verdict = self.correlator.correlate(context.genome_observation)
                matched_id = verdict.matched_genome_id or verdict.created_genome_id or ""
                matched_genome = self._store.get_genome(matched_id) if matched_id else None
                if verdict.decision == "matched" and matched_genome is not None:
                    self.set_genome_context(
                        context.track_id,
                        self._extract_genome_behavioral_signatures(matched_genome),
                    )
                genome_context = self._genome_context_by_track.get(context.track_id)
                if genome_context:
                    context.behavior_context = {
                        **context.behavior_context,
                        "genome_context": dict(genome_context),
                    }
                trajectory_predictions.append(
                    self.trajectory_predictor.predict(
                        context=context,
                        correlation_verdict=verdict,
                        matched_genome=matched_genome,
                    )
                )

            swarm_predictions = self.swarm_analyzer.analyze(
                trajectory_predictions=trajectory_predictions,
                defended_asset_position_m=self.defended_asset_position_m,
                defended_asset_name_en=self.defended_asset_name_en,
                defended_asset_name_ar=self.defended_asset_name_ar,
            )
            commands = self.preposition_optimizer.optimize(
                trajectory_predictions=trajectory_predictions,
                interceptor_profiles=list(self._interceptor_profiles.values()),
                now_s=current_time_s,
            )
            allocator_outcomes = self._cue_allocator(trajectory_predictions)
            interceptor_actions = self._cue_interceptors(commands)
            alerts = self._build_alerts(trajectory_predictions, swarm_predictions)
            posture_level = self._derive_posture_level(trajectory_predictions, swarm_predictions)
            summary_en, summary_ar = self._summaries(
                posture_level=posture_level,
                track_count=len(trajectory_predictions),
                swarm_count=len(swarm_predictions),
                command_count=len(commands),
            )
            posture = DefensePosture(
                posture_level=posture_level,
                summary_en=summary_en,
                summary_ar=summary_ar,
                trajectory_predictions=trajectory_predictions,
                swarm_predictions=swarm_predictions,
                preposition_commands=commands,
                alerts=alerts,
                allocator_outcomes=allocator_outcomes,
                interceptor_actions=interceptor_actions,
                generated_at_s=current_time_s,
            )
            self._last_posture = posture
            return posture

    def get_last_posture(self) -> Optional[DefensePosture]:
        with self._lock:
            return self._last_posture

    def process_tracks(self, tracks: Optional[List[Any]] = None, *, now_s: Optional[float] = None) -> DefensePosture:
        """Compatibility wrapper used by radar/air-defense integrations."""
        return self.process_cycle(tracks=tracks, now_s=now_s)

    def set_genome_context(self, track_id: str, context: Dict[str, Any]) -> None:
        """Persist per-track genome context for downstream trajectory cueing."""
        track_key = str(track_id).strip()
        if not track_key:
            return
        if not isinstance(context, dict):
            return
        with self._lock:
            self._genome_context_by_track[track_key] = dict(context)

    def get_genome_context(self, track_id: str) -> Dict[str, Any]:
        track_key = str(track_id).strip()
        if not track_key:
            return {}
        with self._lock:
            return dict(self._genome_context_by_track.get(track_key, {}))

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            correlator_stats = self.correlator.stats()
            return {
                "correlator": correlator_stats,
                "interceptor_profiles": len(self._interceptor_profiles),
                "has_last_posture": self._last_posture is not None,
                "genome_context_tracks": len(self._genome_context_by_track),
            }

    def _collect_tracks(self) -> List[Any]:
        if self.radar_manager is None:
            return []
        try:
            return self.radar_manager.list_tracks()
        except Exception:
            # Tactical resilience: prediction cycle should survive transient sensor errors.
            return []

    def _cue_allocator(self, predictions: List[ThreatTrajectoryPrediction]) -> List[Dict[str, Any]]:
        if self.target_allocator is None:
            return []
        outcomes: List[Dict[str, Any]] = []
        for prediction in predictions:
            position = prediction.predicted_positions_m.get(60) or prediction.predicted_positions_m.get(120)
            speed = prediction.predicted_speeds_mps.get(60) or prediction.predicted_speeds_mps.get(120) or 0.0
            if position is None:
                continue
            try:
                outcome = self.target_allocator.allocate(
                    target_id=prediction.track_id,
                    target_position=position,
                    target_speed_mps=float(speed),
                    target_classification="ENEMY_UAV",
                )
                outcomes.append(_serialize(outcome))
            except Exception as exc:
                outcomes.append({"target_id": prediction.track_id, "error": str(exc)})
        return outcomes

    def _cue_interceptors(self, commands: List[Any]) -> List[Dict[str, Any]]:
        if self.interceptor_manager is None:
            return []
        actions: List[Dict[str, Any]] = []
        for command in commands:
            assign_ok = False
            launch_ok = False
            launch_now = bool(getattr(command, "launch_now", False))
            radar_acquired_ok: Optional[bool] = None
            try:
                assign_ok = bool(
                    self.interceptor_manager.assign_target(
                        interceptor_id=command.interceptor_id,
                        target_id=command.target_track_id,
                    )
                )
                launch_ok = bool(self.interceptor_manager.launch(command.interceptor_id))
                if launch_now and launch_ok:
                    radar_acquired = getattr(self.interceptor_manager, "radar_acquired", None)
                    if callable(radar_acquired):
                        # Tactical context: launch-now predictive commands must
                        # transition immediately to radar-acquired guidance.
                        radar_acquired_ok = bool(radar_acquired(command.interceptor_id))
            except Exception as exc:
                actions.append(
                    {
                        "interceptor_id": command.interceptor_id,
                        "target_track_id": command.target_track_id,
                        "error": str(exc),
                    }
                )
                continue
            actions.append(
                {
                    "interceptor_id": command.interceptor_id,
                    "target_track_id": command.target_track_id,
                    "assign_ok": assign_ok,
                    "launch_ok": launch_ok,
                    "launch_now": launch_now,
                    "radar_acquired_ok": radar_acquired_ok,
                }
            )
        return actions

    @staticmethod
    def _extract_genome_behavioral_signatures(matched_genome: Any) -> Dict[str, Any]:
        approach_bearing: Optional[Any] = None
        speed_range: Optional[Tuple[float, float]] = None
        temporal_patterns: Dict[str, Any] = {}
        signatures = getattr(matched_genome, "signatures", {}) or {}
        for signature in signatures.values():
            movement = dict(getattr(signature, "movement_patterns", {}) or {})
            temporal = dict(getattr(signature, "temporal_patterns", {}) or {})
            if approach_bearing is None:
                if "approach_vector_deg" in movement:
                    approach_bearing = float(movement["approach_vector_deg"])
                elif "approach_bearing_deg" in movement:
                    approach_bearing = float(movement["approach_bearing_deg"])
                elif "heading_deg" in movement and isinstance(movement["heading_deg"], (list, tuple)):
                    values = movement["heading_deg"]
                    if len(values) == 2:
                        approach_bearing = (float(values[0]), float(values[1]))
                elif "bearing_range_deg" in movement and isinstance(movement["bearing_range_deg"], (list, tuple)):
                    values = movement["bearing_range_deg"]
                    if len(values) == 2:
                        approach_bearing = (float(values[0]), float(values[1]))
                elif "approach_vector_range_deg" in movement and isinstance(
                    movement["approach_vector_range_deg"], (list, tuple)
                ):
                    values = movement["approach_vector_range_deg"]
                    if len(values) == 2:
                        approach_bearing = (float(values[0]), float(values[1]))
            if speed_range is None:
                if "speed_range_mps" in movement and isinstance(movement["speed_range_mps"], (list, tuple)):
                    values = movement["speed_range_mps"]
                    if len(values) == 2:
                        speed_range = (float(values[0]), float(values[1]))
                elif "speed_mps" in movement and isinstance(movement["speed_mps"], (list, tuple)):
                    values = movement["speed_mps"]
                    if len(values) == 2:
                        speed_range = (float(values[0]), float(values[1]))
                elif "speed_min_mps" in movement and "speed_max_mps" in movement:
                    speed_range = (float(movement["speed_min_mps"]), float(movement["speed_max_mps"]))
            if temporal and not temporal_patterns:
                temporal_patterns = temporal
        return {
            "approach_bearing": approach_bearing,
            "speed_range": speed_range,
            "temporal_patterns": temporal_patterns,
            "matched_genome_id": str(getattr(matched_genome, "genome_id", "")),
            "matched_genome_name": str(getattr(matched_genome, "actor_name", "")),
        }

    def _build_alerts(self, predictions: List[ThreatTrajectoryPrediction], swarm_predictions: List[Any]) -> List[PredictiveAlert]:
        alerts: List[PredictiveAlert] = []
        high_risk = [prediction for prediction in predictions if prediction.risk_score >= 0.7]
        if high_risk:
            track_ids = [prediction.track_id for prediction in high_risk]
            alerts.append(
                PredictiveAlert(
                    level="high",
                    message_en=f"{len(track_ids)} high-risk trajectories forecast toward defended zone",
                    message_ar=f"تم توقع {len(track_ids)} مسارات عالية الخطورة نحو منطقة الدفاع",
                    related_track_ids=track_ids,
                    confidence=min(0.99, sum(prediction.risk_score for prediction in high_risk) / len(high_risk)),
                    recommended_actions_en=[
                        "Pre-launch available interceptors",
                        "Reserve medium-range effectors for follow-on wave",
                    ],
                    recommended_actions_ar=[
                        "الإطلاق المسبق للاعتراضات المتاحة",
                        "حجز المؤثرات متوسطة المدى للموجة التالية",
                    ],
                )
            )
        for swarm in swarm_predictions:
            if swarm.intent_classification != "saturation attack":
                continue
            alerts.append(
                PredictiveAlert(
                    level="critical",
                    message_en=f"Swarm {swarm.swarm_id} classified as saturation attack",
                    message_ar=f"تم تصنيف السرب {swarm.swarm_id} كهجوم إغراق",
                    related_track_ids=swarm.member_track_ids,
                    confidence=swarm.intent_confidence,
                    recommended_actions_en=[
                        "Commit interceptor reserve immediately",
                        "Queue CIWS and EW fallback layers",
                    ],
                    recommended_actions_ar=[
                        "تفعيل احتياطي الاعتراض فوراً",
                        "تجهيز طبقات المدافع والحرب الإلكترونية الاحتياطية",
                    ],
                )
            )
        return alerts

    @staticmethod
    def _derive_posture_level(predictions: List[ThreatTrajectoryPrediction], swarm_predictions: List[Any]) -> str:
        max_risk = max((prediction.risk_score for prediction in predictions), default=0.0)
        saturation = any(swarm.intent_classification == "saturation attack" for swarm in swarm_predictions)
        if saturation or max_risk >= 0.8:
            return "critical"
        if max_risk >= 0.55 or len(swarm_predictions) > 0:
            return "elevated"
        return "guarded"

    @staticmethod
    def _summaries(*, posture_level: str, track_count: int, swarm_count: int, command_count: int) -> Tuple[str, str]:
        summary_en = (
            f"Posture {posture_level}: analyzed {track_count} tracks, "
            f"detected {swarm_count} swarms, issued {command_count} pre-position commands."
        )
        summary_ar = (
            f"الوضع {posture_level}: تم تحليل {track_count} مسارات، "
            f"واكتشاف {swarm_count} أسراب، وإصدار {command_count} أوامر تموضع استباقي."
        )
        return summary_en, summary_ar
