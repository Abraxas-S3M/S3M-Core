"""Unit tests for Bayesian risk assessment subsystem.

Military context:
Tests verify risk fusion correctness, threshold behavior, and bilingual
recommendation outputs used by commanders for mission authorization.
"""

from datetime import datetime, timezone

from services.risk_assessment.bayesian_network import BayesianRiskNetwork
from services.risk_assessment.cost_estimator import CostEstimator
from services.risk_assessment.models import RiskAssessment, RiskCategory, RiskFactor, RiskLevel
from services.risk_assessment.risk_engine import RiskEngine


def _factor(name, category, score, weight=0.25, confidence=0.8):
    return RiskFactor(
        factor_id=name,
        name=name,
        category=category,
        weight=weight,
        score=score,
        confidence=confidence,
        source="test",
        detail=name,
        mitigations=["mitigate"],
    )


def test_bayesian_network_computes_risk_from_cpt_tables():
    net = BayesianRiskNetwork()
    factors = [
        _factor("threat_environment", RiskCategory.STRATEGIC_IMPACT, 0.8),
        _factor("equipment_condition", RiskCategory.EQUIPMENT_LOSS, 0.7),
        _factor("personnel_readiness", RiskCategory.PERSONNEL_CASUALTY, 0.4),
        _factor("mission_complexity", RiskCategory.MISSION_FAILURE, 0.5),
    ]
    out = net.compute(factors)
    assert 0.0 <= out["equipment_loss_probability"] <= 1.0
    assert 0.0 <= out["overall_score"] <= 100.0


def test_high_threat_plus_poor_equipment_leads_to_high_risk_score():
    net = BayesianRiskNetwork()
    factors = [
        _factor("threat_environment", RiskCategory.STRATEGIC_IMPACT, 0.95),
        _factor("equipment_condition", RiskCategory.EQUIPMENT_LOSS, 0.95),
        _factor("personnel_readiness", RiskCategory.PERSONNEL_CASUALTY, 0.7),
        _factor("mission_complexity", RiskCategory.MISSION_FAILURE, 0.7),
    ]
    out = net.compute(factors)
    assert out["overall_score"] > 50.0


def test_good_training_partially_compensates_for_higher_threat():
    net = BayesianRiskNetwork()
    poor_training = net.compute(
        [
            _factor("threat_environment", RiskCategory.STRATEGIC_IMPACT, 0.8),
            _factor("equipment_condition", RiskCategory.EQUIPMENT_LOSS, 0.4),
            _factor("personnel_readiness", RiskCategory.PERSONNEL_CASUALTY, 0.8),
            _factor("mission_complexity", RiskCategory.MISSION_FAILURE, 0.5),
        ]
    )
    good_training = net.compute(
        [
            _factor("threat_environment", RiskCategory.STRATEGIC_IMPACT, 0.8),
            _factor("equipment_condition", RiskCategory.EQUIPMENT_LOSS, 0.4),
            _factor("personnel_readiness", RiskCategory.PERSONNEL_CASUALTY, 0.2),
            _factor("mission_complexity", RiskCategory.MISSION_FAILURE, 0.5),
        ]
    )
    assert good_training["personnel_casualty_probability"] <= poor_training["personnel_casualty_probability"]


def test_risk_engine_assess_mission_collects_factors_from_layers():
    engine = RiskEngine()
    assessment = engine.assess_mission(
        mission={"name": "Patrol", "objectives": 3, "duration_hours": 4, "gps_denial_probability": 0.3},
        assets=[{"type": "uav_quadrotor_small", "condition_score": 0.4}],
        personnel=[{"readiness": 0.9}],
    )
    assert len(assessment.risk_factors) >= 7


def test_risk_level_thresholds_score20_green_score60_red():
    assessment_green = RiskAssessment(
        assessment_id="A1",
        context="mission",
        timestamp=datetime.now(timezone.utc),
        equipment_loss_prob=0.1,
        personnel_casualty_prob=0.1,
        mission_failure_prob=0.1,
        cost_estimate_usd=1000,
        risk_level=RiskLevel.GREEN,
        risk_factors=[],
        overall_score=20,
        interaction_effects=[],
        recommendation_en="ok",
        recommendation_ar="ok",
        llm_analysis=None,
        approved_by=None,
        xai_explanation="x",
    )
    assessment_red = RiskAssessment(
        assessment_id="A2",
        context="mission",
        timestamp=datetime.now(timezone.utc),
        equipment_loss_prob=0.6,
        personnel_casualty_prob=0.6,
        mission_failure_prob=0.6,
        cost_estimate_usd=1000,
        risk_level=RiskLevel.RED,
        risk_factors=[],
        overall_score=60,
        interaction_effects=[],
        recommendation_en="ok",
        recommendation_ar="ok",
        llm_analysis=None,
        approved_by=None,
        xai_explanation="x",
    )
    assert assessment_green.risk_level == RiskLevel.GREEN
    assert assessment_red.risk_level == RiskLevel.RED


def test_cost_estimator_computes_expected_loss_correctly():
    est = CostEstimator()
    cost = est.estimate_equipment_cost([{"type": "uav_quadrotor_small"}, {"type": "ugv_wheeled_small"}], 0.5)
    assert cost == (50_000 + 200_000) * 0.5


def test_bilingual_recommendations_generated():
    engine = RiskEngine()
    a = engine.assess_patrol(route=[(0, 0), (1, 1)], assets=[{"type": "uav_quadrotor_small", "condition_score": 0.4}])
    assert a.recommendation_en
    assert a.recommendation_ar
