"""Facade for probabilistic tactical decision-making pipeline.

The pipeline fuses Bayesian threat reasoning, state estimation under sensor
noise, POMDP policy selection, and mission trade-off optimization.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional
import uuid

from src.autonomy.models import AutonomyDecision, DecisionType
from src.autonomy.rl.environments import MilitaryEnvironment

from .bayesian_net import BayesianThreatNet
from .belief_state import BeliefState
from .multi_objective import ParetoOptimizer
from .particle_filter import TacticalParticleFilter
from .pomdp_solver import POMDPSolver


class ProbabilisticDecisionEngine:
    """End-to-end probabilistic autonomy engine with ROE hard checks."""

    def __init__(self, n_particles: int = 200, agent_id: str = "decision_engine") -> None:
        self.agent_id = str(agent_id)
        self.belief_state = BeliefState()
        self.bayesian_net = BayesianThreatNet()
        self.particle_filter = TacticalParticleFilter(n_particles=n_particles, dt=1.0)
        self.pomdp = POMDPSolver(discount=0.95, horizon=6)
        self.optimizer = ParetoOptimizer()
        self.audit_log: List[AutonomyDecision] = []
        self.last_result: Dict[str, Any] = {}

    def _to_decision_type(self, action_name: str) -> DecisionType:
        mapping = {
            "engage": DecisionType.ENGAGE,
            "advance": DecisionType.PURSUE,
            "retreat": DecisionType.RETREAT,
            "evade": DecisionType.AVOID,
            "hold": DecisionType.HOLD,
            "recon": DecisionType.REPLAN,
        }
        return mapping.get(action_name, DecisionType.HOLD)

    def _to_env_action(self, action_name: str) -> int:
        mapping = {
            "engage": MilitaryEnvironment.ACTION_ENGAGE,
            "advance": MilitaryEnvironment.ACTION_MOVE_FORWARD,
            "retreat": MilitaryEnvironment.ACTION_DECELERATE,
            "evade": MilitaryEnvironment.ACTION_TURN_RIGHT,
            "hold": MilitaryEnvironment.ACTION_HOLD,
            "recon": MilitaryEnvironment.ACTION_TURN_LEFT,
        }
        return int(mapping.get(action_name, MilitaryEnvironment.ACTION_HOLD))

    def _nearest_threat_distance(self, observation: Dict[str, Any]) -> float:
        pos = observation.get("agent_position", [0.0, 0.0, 0.0])
        if isinstance(pos, tuple):
            pos = list(pos)
        if not isinstance(pos, list) or len(pos) < 2:
            pos = [0.0, 0.0, 0.0]
        threat_positions = observation.get("threat_positions", [])
        if not isinstance(threat_positions, list) or not threat_positions:
            return float("inf")
        nearest = float("inf")
        for t in threat_positions:
            if not isinstance(t, (list, tuple)) or len(t) < 2:
                continue
            dx = float(t[0]) - float(pos[0])
            dy = float(t[1]) - float(pos[1])
            d = math.sqrt(dx * dx + dy * dy)
            if d < nearest:
                nearest = d
        return nearest

    def _extract_evidence(self, observation: Dict[str, Any]) -> Dict[str, str]:
        threat_levels = observation.get("threat_levels", []) or []
        nearest = self._nearest_threat_distance(observation)
        avg_lvl = 0.3
        if isinstance(threat_levels, list) and threat_levels:
            avg_lvl = sum(float(v) for v in threat_levels) / max(1, len(threat_levels))
        sensor_return = "weak"
        if avg_lvl >= 0.75 or nearest < 15.0:
            sensor_return = "strong"
        elif avg_lvl <= 0.2 and nearest > 60.0:
            sensor_return = "none"

        if nearest < 15.0:
            behavior_pattern = "aggressive"
        elif nearest < 40.0:
            behavior_pattern = "suspicious"
        else:
            behavior_pattern = "normal"

        if avg_lvl > 0.65:
            electronic_signature = "high"
        elif avg_lvl > 0.3:
            electronic_signature = "low"
        else:
            electronic_signature = "none"

        return {
            "sensor_return": sensor_return,
            "behavior_pattern": behavior_pattern,
            "electronic_signature": electronic_signature,
        }

    def _objectives_for_action(
        self,
        action: str,
        observation: Dict[str, Any],
        engagement_risk: float,
        hostile_prob: float,
    ) -> Dict[str, float]:
        speed = float((observation.get("agent_speed", [0.0]) or [0.0])[0])
        roe = str(observation.get("rules_of_engagement", "weapons_hold")).lower()
        nearest = self._nearest_threat_distance(observation)

        base = {
            "survival": 0.7,
            "mission_progress": 0.4,
            "roe_risk": 0.15,
            "fuel_cost": min(1.0, 0.2 + speed / 25.0),
            "info_gain": 0.4,
        }
        if action == "advance":
            base["survival"] = max(0.1, 0.85 - engagement_risk)
            base["mission_progress"] = 0.85
            base["roe_risk"] = 0.2
            base["fuel_cost"] = min(1.0, 0.35 + speed / 20.0)
            base["info_gain"] = 0.45
        elif action == "hold":
            base["survival"] = 0.75
            base["mission_progress"] = 0.35
            base["roe_risk"] = 0.05
            base["fuel_cost"] = 0.1
            base["info_gain"] = 0.35
        elif action == "retreat":
            base["survival"] = min(1.0, 0.92 + engagement_risk * 0.05)
            base["mission_progress"] = 0.15
            base["roe_risk"] = 0.03
            base["fuel_cost"] = 0.4
            base["info_gain"] = 0.2
        elif action == "engage":
            base["survival"] = max(0.1, 0.65 - engagement_risk * 0.4)
            base["mission_progress"] = 0.78 if hostile_prob > 0.6 else 0.4
            base["roe_risk"] = 0.88 if roe == "weapons_hold" else 0.45
            base["fuel_cost"] = 0.6
            base["info_gain"] = 0.5
        elif action == "evade":
            base["survival"] = min(1.0, 0.8 + engagement_risk * 0.15)
            base["mission_progress"] = 0.3
            base["roe_risk"] = 0.08
            base["fuel_cost"] = 0.5
            base["info_gain"] = 0.28
        elif action == "recon":
            base["survival"] = 0.68
            base["mission_progress"] = 0.42
            base["roe_risk"] = 0.06
            base["fuel_cost"] = 0.2
            base["info_gain"] = 0.9

        if nearest < 20.0 and action in {"retreat", "evade"}:
            base["survival"] = min(1.0, base["survival"] + 0.08)
        return {k: max(0.0, min(1.0, float(v))) for k, v in base.items()}

    def _log_decision(
        self,
        observation: Dict[str, Any],
        action_name: str,
        action_id: int,
        confidence: float,
        risk: float,
        rationale: str,
        alternatives: List[Dict[str, Any]],
        metadata: Dict[str, Any],
    ) -> None:
        decision = AutonomyDecision(
            decision_id=f"dec-{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc),
            decision_type=self._to_decision_type(action_name),
            agent_id=str(observation.get("agent_id", self.agent_id)),
            mission_id=observation.get("mission_id"),
            context=dict(observation),
            action_taken={"action": action_name, "action_id": int(action_id), **metadata},
            alternatives_considered=list(alternatives),
            confidence=max(0.0, min(1.0, float(confidence))),
            reasoning=rationale,
            llm_consulted=False,
            requires_human_review=False,
            risk_score=max(0.0, min(1.0, float(risk))),
        )
        self.audit_log.append(decision)
        if len(self.audit_log) > 10000:
            self.audit_log = self.audit_log[-10000:]

    def predict(self, observation: Dict[str, Any]) -> int:
        """Predict environment action ID from one tactical observation."""
        track_id = str(observation.get("track_id", "primary"))
        if track_id not in self.belief_state.snapshot():
            self.belief_state.initialize_track(track_id=track_id, hostile_prior=0.5)

        evidence = self._extract_evidence(observation)
        assessment = self.bayesian_net.assess(evidence)
        engagement_risk = float(assessment["threat_score"])
        intent_attack_prob = float(assessment["intent"].get("attack", 0.0))
        hostile_likelihood = 0.3 + 0.7 * max(engagement_risk, intent_attack_prob)
        benign_likelihood = max(0.05, 1.05 - hostile_likelihood)
        belief_update = self.belief_state.bayesian_update(
            track_id=track_id,
            likelihood_hostile=hostile_likelihood,
            likelihood_non_hostile=benign_likelihood,
            evidence_confidence=0.9,
            intent_hint="attack" if intent_attack_prob > 0.5 else "observe",
        )
        hostile_prob = float(belief_update["hostile_probability"])

        agent_pos = observation.get("agent_position", [0.0, 0.0, 0.0])
        if isinstance(agent_pos, tuple):
            agent_pos = list(agent_pos)
        if not isinstance(agent_pos, list) or len(agent_pos) < 3:
            agent_pos = [0.0, 0.0, 0.0]
        obs_heading_deg = float((observation.get("agent_heading", [0.0]) or [0.0])[0])
        bearing = math.radians(obs_heading_deg)
        pf_observation = {
            "x": float(agent_pos[0]),
            "y": float(agent_pos[1]),
            "z": float(agent_pos[2]),
            "bearing": bearing,
            "intent": hostile_prob,
        }
        self.particle_filter.predict()
        self.particle_filter.update(pf_observation)
        estimate = self.particle_filter.estimate()

        nearest = self._nearest_threat_distance(observation)
        if hostile_prob > 0.8 and nearest < 20.0:
            pomdp_obs = "firefight"
        elif hostile_prob > 0.6 or nearest < 35.0:
            pomdp_obs = "contact"
        else:
            pomdp_obs = "clear"
        belief = self.pomdp.belief_update(action="hold", observation=pomdp_obs)
        pomdp_action = self.pomdp.select_action(belief)

        vectors: Dict[str, Dict[str, float]] = {}
        for action in self.pomdp.actions:
            vectors[action] = self._objectives_for_action(
                action=action,
                observation=observation,
                engagement_risk=engagement_risk,
                hostile_prob=hostile_prob,
            )
        frontier = self.optimizer.pareto_frontier(vectors)
        selected_name, score, explanation = self.optimizer.select_action(
            vectors=vectors,
            method="topsis",
            fallback=pomdp_action,
        )
        frontier_size = len(frontier)

        roe = str(observation.get("rules_of_engagement", "weapons_hold")).lower()
        roe_override = None
        if roe == "weapons_hold" and (selected_name == "engage" or nearest < 25.0):
            selected_name = "hold"
            roe_override = "ENGAGE blocked under weapons_hold"

        action_id = self._to_env_action(selected_name)
        score_map = explanation.get("scores", {}) if isinstance(explanation, dict) else {}
        alternatives = [
            {"action": str(name), "score": float(val)}
            for name, val in sorted(score_map.items(), key=lambda item: item[1], reverse=True)
            if str(name) != selected_name
        ]
        rationale = (
            "Probabilistic pipeline selected action after Bayesian threat inference, "
            "particle-filtered tracking, POMDP tactical policy evaluation, and Pareto trade-off scoring."
        )
        metadata = {
            "decision_type": "pareto_selection",
            "pomdp_action": pomdp_action,
            "frontier_size": frontier_size,
            "threat_posterior": hostile_prob,
            "track_estimate": estimate,
            "bayesian_assessment": assessment,
            "tradeoff_explanation": explanation.get("tradeoff", {}) if isinstance(explanation, dict) else {},
        }
        if roe_override:
            metadata["roe_override"] = roe_override
        self._log_decision(
            observation=observation,
            action_name=selected_name,
            action_id=action_id,
            confidence=min(1.0, max(0.0, score)),
            risk=min(1.0, max(0.0, engagement_risk)),
            rationale=rationale,
            alternatives=alternatives,
            metadata=metadata,
        )
        self.last_result = {
            "action_name": selected_name,
            "action_id": action_id,
            "engagement_risk": engagement_risk,
            "hostile_probability": hostile_prob,
            "particle_estimate": estimate,
            "pomdp_action": pomdp_action,
            "pareto_frontier": frontier,
            "tradeoff_explanation": explanation,
            "roe_override": roe_override,
        }
        return int(action_id)
