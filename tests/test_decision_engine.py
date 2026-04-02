"""Tests for probabilistic autonomy decision engine modules."""

from __future__ import annotations

from src.autonomy.decision_engine import (
    BayesianThreatNet,
    BeliefState,
    ParetoOptimizer,
    POMDPSolver,
    ProbabilisticDecisionEngine,
    TacticalParticleFilter,
)
from src.autonomy.rl.environments import MilitaryEnvironment


def test_belief_state_init_update_entropy_reduction() -> None:
    belief = BeliefState()
    belief.initialize_track("trk-1", hostile_prior=0.5)
    before = belief.track_entropy("trk-1")
    update = belief.bayesian_update(
        "trk-1",
        likelihood_hostile=0.9,
        likelihood_non_hostile=0.2,
        evidence_confidence=1.0,
    )
    after = belief.track_entropy("trk-1")
    assert update["hostile_probability"] > 0.5
    assert after < before


def test_bayesian_net_inference_with_evidence() -> None:
    net = BayesianThreatNet()
    result = net.infer(
        "engagement_risk",
        {
            "sensor_return": "strong",
            "behavior_pattern": "aggressive",
            "electronic_signature": "high",
        },
    )
    assert abs(sum(result.values()) - 1.0) < 1e-6
    assert result["high"] > result["low"]


def test_particle_filter_tracking_convergence() -> None:
    pf = TacticalParticleFilter(n_particles=300, dt=1.0, seed=7)
    pf.initialize((0.0, 0.0, 0.0), position_std=10.0, velocity_std=1.0, intent_prior=0.3)
    for _ in range(8):
        pf.predict()
        pf.update({"x": 50.0, "y": 20.0, "z": 0.0, "bearing": 0.0, "intent": 0.8})
    estimate = pf.estimate()
    assert abs(estimate["x"] - 50.0) < 15.0
    assert abs(estimate["y"] - 20.0) < 15.0
    assert 0.0 <= estimate["intent"] <= 1.0


def test_pomdp_solve_and_action_selection() -> None:
    solver = POMDPSolver(discount=0.95, horizon=6)
    solver.solve(iterations=10)
    belief = solver.belief_update("hold", "threat_detected")
    action = solver.select_action(belief)
    assert action in solver.actions
    assert abs(sum(belief.values()) - 1.0) < 1e-6


def test_pareto_frontier_identification() -> None:
    optimizer = ParetoOptimizer()
    vectors = {
        "a": {"survival": 0.9, "mission_progress": 0.4, "roe_risk": 0.2, "fuel_cost": 0.2, "info_gain": 0.2},
        "b": {"survival": 0.8, "mission_progress": 0.9, "roe_risk": 0.4, "fuel_cost": 0.4, "info_gain": 0.4},
        "c": {"survival": 0.3, "mission_progress": 0.3, "roe_risk": 0.9, "fuel_cost": 0.9, "info_gain": 0.1},
    }
    frontier = optimizer.pareto_frontier(vectors)
    assert "c" not in frontier
    assert "a" in frontier or "b" in frontier


def test_full_engine_pipeline_with_roe_override() -> None:
    engine = ProbabilisticDecisionEngine()
    observation = {
        "agent_id": "agent-1",
        "agent_position": [10.0, 10.0, 0.0],
        "agent_heading": [45.0],
        "agent_speed": [6.0],
        "threat_positions": [[14.0, 13.0, 0.0]],
        "threat_levels": [0.95],
        "mission_waypoint": [100.0, 100.0, 0.0],
        "rules_of_engagement": "weapons_hold",
        "track_id": "trk-1",
    }
    action = engine.predict(observation)
    assert action == MilitaryEnvironment.ACTION_HOLD
    assert engine.audit_log
    assert engine.last_result.get("roe_override") is not None
