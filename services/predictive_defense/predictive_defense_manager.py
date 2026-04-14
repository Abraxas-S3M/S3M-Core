"""Orchestrates the full predictive defense pipeline.

Military context:
This is the engine that gives S3M its doctrinal advantage. Every radar
update cycle, it:
1. Converts fused tracks to entity snapshots and genome observations
2. Correlates tracks with threat genome library
3. Produces genome-enhanced trajectory predictions
4. Analyzes swarm behavior and convergence
5. Computes interceptor pre-positioning commands
6. Generates predictive alerts with recommended defense posture
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

from services.predictive_defense.models import (
    DefensePosture,
    PredictiveAlert,
    PrePositionCommand,
    SwarmPrediction,
    ThreatTrajectoryPrediction,
)
from services.predictive_defense.preposition_optimizer import PrePositionOptimizer
from services.predictive_defense.swarm_analyzer import SwarmAnalyzer
from services.predictive_defense.track_genome_bridge import TrackGenomeBridge
from services.predictive_defense.trajectory_predictor import TrajectoryPredictor
from src.prediction.short_horizon_predictor import ShortHorizonPredictor
from src.sensor_fusion.models import Track, TrackState


class PredictiveDefenseManager:
    """Central orchestrator for predictive threat defense."""

    def __init__(
        self,
        defended_position: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        outer_zone_radius_m: float = 40000.0,
        interceptor_speed_mps: float = 60.0,
    ) -> None:
        self._lock = threading.RLock()
        self.defended_position = defended_position

        self.bridge = TrackGenomeBridge()
        self.predictor = TrajectoryPredictor(
            predictor=ShortHorizonPredictor(windows_s=[30.0, 60.0, 120.0]),
            defended_position=defended_position,
            outer_zone_radius_m=outer_zone_radius_m,
        )
        self.swarm_analyzer = SwarmAnalyzer()
        self.optimizer = PrePositionOptimizer(
            interceptor_speed_mps=interceptor_speed_mps,
            defended_position=defended_position,
        )

        self._predictions: List[ThreatTrajectoryPrediction] = []
        self._swarm: Optional[SwarmPrediction] = None
        self._alerts: List[PredictiveAlert] = []
        self._commands: List[PrePositionCommand] = []

        # Genome context cache: track_id -> genome features
        self._genome_contexts: Dict[str, Dict[str, Any]] = {}

    def set_genome_context(self, track_id: str, context: Dict[str, Any]) -> None:
        """Attach genome correlation context to a track."""
        if not isinstance(track_id, str) or not track_id.strip():
            raise ValueError("track_id must be a non-empty string")
        if not isinstance(context, dict):
            raise ValueError("context must be a dictionary")
        with self._lock:
            self._genome_contexts[track_id] = context

    def process_tracks(
        self,
        confirmed_tracks: List[Track],
        available_interceptors: Optional[List[Dict[str, Any]]] = None,
    ) -> PredictiveAlert:
        """Run the full predictive defense pipeline on current tracks.

        Returns a PredictiveAlert with recommended posture and pre-position commands.
        """
        with self._lock:
            # Step 1-2: Convert tracks and predict trajectories
            predictions = []
            for track in confirmed_tracks:
                if track.state != TrackState.CONFIRMED:
                    continue
                entity = self.bridge.track_to_entity_snapshot(track)
                genome_ctx = self._genome_contexts.get(track.track_id)
                pred = self.predictor.predict(entity, genome_ctx)
                predictions.append(pred)

            self._predictions = predictions

            # Step 3: Swarm analysis
            self._swarm = self.swarm_analyzer.analyze(predictions, self.defended_position)

            # Step 4: Pre-positioning
            interceptors = available_interceptors or []
            if predictions and interceptors:
                self._commands = self.optimizer.optimize_preposition(
                    predictions, interceptors, self._swarm
                )
            else:
                self._commands = []

            # Step 5: Generate alert
            alert = self._generate_alert(predictions, self._swarm, self._commands)
            self._alerts.append(alert)

            # Keep bounded
            if len(self._alerts) > 200:
                self._alerts = self._alerts[-100:]

            return alert

    def _generate_alert(
        self,
        predictions: List[ThreatTrajectoryPrediction],
        swarm: Optional[SwarmPrediction],
        commands: List[PrePositionCommand],
    ) -> PredictiveAlert:
        """Generate a predictive defense alert based on current analysis."""
        if not predictions:
            return PredictiveAlert(
                severity="low",
                posture=DefensePosture.NORMAL,
                title_en="No active threats detected",
                title_ar="لا توجد تهديدات نشطة",
            )

        # Determine urgency from closest threat
        min_time = min(p.time_to_asset_s for p in predictions) if predictions else 9999
        threat_count = len(predictions)

        if min_time < 30:
            severity = "critical"
            posture = DefensePosture.IMMINENT
        elif min_time < 90:
            severity = "high"
            posture = DefensePosture.PRE_POSITION
        elif min_time < 300:
            severity = "medium"
            posture = DefensePosture.ELEVATED
        else:
            severity = "low"
            posture = DefensePosture.NORMAL

        actions = []
        if commands:
            actions.append(f"Pre-position {len(commands)} interceptor(s)")
            launch_now = [c for c in commands if c.launch_now]
            if launch_now:
                actions.append(f"LAUNCH NOW: {len(launch_now)} interceptor(s)")

        if swarm:
            actions.append(f"Swarm detected: {swarm.track_count} tracks, intent={swarm.intent.value}")
            actions.append(f"Convergence in {swarm.convergence_time_s:.0f}s")

        genome_names = list({p.genome_match for p in predictions if p.genome_match})
        if genome_names:
            actions.append(f"Genome match: {', '.join(genome_names)}")

        return PredictiveAlert(
            severity=severity,
            posture=posture,
            title_en=f"{threat_count} threat(s) predicted — {posture.value}",
            title_ar=f"{threat_count} تهديد(ات) متوقعة — {posture.value}",
            description=f"Predicted {threat_count} threats, closest arrival in {min_time:.0f}s",
            threat_count=threat_count,
            time_to_impact_s=min_time,
            recommended_actions=actions,
            pre_position_commands=commands,
        )

    def get_predictions(self) -> List[ThreatTrajectoryPrediction]:
        with self._lock:
            return list(self._predictions)

    def get_swarm_analysis(self) -> Optional[SwarmPrediction]:
        with self._lock:
            return self._swarm

    def get_commands(self) -> List[PrePositionCommand]:
        with self._lock:
            return list(self._commands)

    def get_alerts(self, limit: int = 20) -> List[PredictiveAlert]:
        with self._lock:
            return self._alerts[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active_predictions": len(self._predictions),
                "swarm_detected": self._swarm is not None,
                "swarm_size": self._swarm.track_count if self._swarm else 0,
                "pre_position_commands": len(self._commands),
                "alerts_generated": len(self._alerts),
                "genome_contexts_cached": len(self._genome_contexts),
            }
