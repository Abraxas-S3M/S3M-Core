"""Risk engine aggregating evidence across S3M layers.

Military context:
This engine evaluates operational risk before mission launch or engagement by
combining threat, readiness, sustainment, environment, and EW indicators.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List
import uuid

from services.risk_assessment.bayesian_network import BayesianRiskNetwork
from services.risk_assessment.cost_estimator import CostEstimator
from services.risk_assessment.models import RiskAssessment, RiskCategory, RiskFactor, RiskLevel, RiskProfile
from src.autonomy.models import AutonomyDecision, DecisionType
from src.autonomy.xai import AssuranceChecker, DecisionExplainer
from src.security.crypto import SecureAuditLog
from src.threat_detection.threat_manager import ThreatManager


class RiskEngine:
    """Collect evidence and compute mission/engagement/patrol risk outputs."""

    def __init__(self):
        self.threat_manager = ThreatManager()
        self.bayes = BayesianRiskNetwork()
        self.cost_estimator = CostEstimator()
        self.assurance = AssuranceChecker(risk_threshold=0.6, confidence_threshold=0.4)
        self.explainer = DecisionExplainer()
        self.audit = SecureAuditLog(log_dir="data/security_audit/risk")
        self._assessments: Dict[str, RiskAssessment] = {}
        self._history: Dict[str, RiskProfile] = {}

    def _factor(self, name: str, category: RiskCategory, score: float, source: str, detail: str, weight: float = 0.2) -> RiskFactor:
        return RiskFactor(
            factor_id=f"rf-{uuid.uuid4().hex[:8]}",
            name=name,
            category=category,
            weight=max(0.0, min(1.0, float(weight))),
            score=max(0.0, min(1.0, float(score))),
            confidence=0.75,
            source=source,
            detail=detail,
            mitigations=["Increase ISR", "Adjust mission profile", "Improve redundancy"],
        )

    def _recommendation_en_ar(self, level: RiskLevel, factors: List[RiskFactor]) -> tuple[str, str]:
        top = sorted(factors, key=lambda f: f.weight * f.score, reverse=True)[:3]
        top_names = ", ".join(f.name for f in top) if top else "baseline"
        if level in {RiskLevel.RED, RiskLevel.BLACK}:
            en = f"High risk detected ({top_names}). Recommend modify mission, add escort and EW fallback, or abort."
            ar = f"تم اكتشاف مخاطر مرتفعة ({top_names}). يوصى بتعديل المهمة أو إضافة مرافقة وخطة حرب إلكترونية أو الإلغاء."
        elif level == RiskLevel.AMBER:
            en = f"Elevated risk ({top_names}). Proceed with caution and additional monitoring."
            ar = f"مخاطر متوسطة ({top_names}). يمكن التنفيذ بحذر مع مراقبة إضافية."
        else:
            en = f"Risk acceptable ({top_names}). Proceed with current controls."
            ar = f"المخاطر مقبولة ({top_names}). يمكن التنفيذ مع الضوابط الحالية."
        return en, ar

    def _build_assessment(self, context: str, factors: List[RiskFactor], assets: List[dict], approved_by: str = None) -> RiskAssessment:
        computed = self.bayes.compute(factors)
        en, ar = self._recommendation_en_ar(computed["risk_level"], factors)

        decision = AutonomyDecision(
            decision_id=f"risk-dec-{uuid.uuid4().hex[:10]}",
            timestamp=datetime.now(timezone.utc),
            decision_type=DecisionType.REPLAN,
            agent_id="risk_engine",
            mission_id=None,
            context={"risk_context": context, "factor_count": len(factors), "rules_of_engagement": "weapons_tight"},
            action_taken={"risk_level": computed["risk_level"].value},
            alternatives_considered=[{"option": "abort", "reason": "if risk exceeds threshold"}],
            confidence=0.8,
            reasoning="Risk synthesis computed from Bayesian network factors.",
            llm_consulted=False,
            requires_human_review=False,
            risk_score=min(1.0, computed["overall_score"] / 100.0),
        )
        assurance = self.assurance.check(decision)
        xai = self.explainer.explain(decision)

        assessment = RiskAssessment(
            assessment_id=f"risk-{uuid.uuid4().hex[:10]}",
            context=context,
            timestamp=datetime.now(timezone.utc),
            equipment_loss_prob=computed["equipment_loss_probability"],
            personnel_casualty_prob=computed["personnel_casualty_probability"],
            mission_failure_prob=computed["mission_failure_probability"],
            cost_estimate_usd=computed["cost_estimate_usd"],
            risk_level=computed["risk_level"],
            risk_factors=factors,
            overall_score=computed["overall_score"],
            interaction_effects=computed["interaction_effects"],
            recommendation_en=en,
            recommendation_ar=ar,
            llm_analysis="Offline sovereign recommendation generated from Bayesian output.",
            approved_by=approved_by,
            xai_explanation=f"{xai.get('summary')} | assurance={assurance['reason']}",
        )

        assessment.cost_estimate_usd = self.cost_estimator.estimate_total_risk_cost(assessment, assets)
        self._assessments[assessment.assessment_id] = assessment
        self.audit.log(
            action="risk_assessment_generated",
            source="risk_engine",
            details={"assessment_id": assessment.assessment_id, "context": context, "risk_level": assessment.risk_level.value},
        )
        return assessment

    def assess_mission(self, mission: dict, assets: List[dict], personnel: List[dict]) -> RiskAssessment:
        """Assess mission-level risk using all primary evidence streams."""
        threat_stats = self.threat_manager.get_stats()
        threat_score = min(1.0, float(threat_stats.get("total_events", 0)) / 20.0)

        equipment_scores = [float(a.get("condition_score", 0.4)) for a in assets] or [0.4]
        equipment_score = max(equipment_scores)

        readiness_values = [1.0 - float(p.get("readiness", 0.7)) for p in personnel] or [0.3]
        personnel_score = sum(readiness_values) / len(readiness_values)

        historical_loss = float(mission.get("historical_loss_rate", 0.2))
        env_score = float(mission.get("environment_risk", 0.3))
        complexity_score = min(1.0, float(mission.get("objectives", 1)) / 8.0 + float(mission.get("duration_hours", 1.0)) / 24.0)
        gps_score = float(mission.get("gps_denial_probability", 0.2))

        factors = [
            self._factor("threat_environment", RiskCategory.STRATEGIC_IMPACT, threat_score, "ThreatManager", "Active threat density"),
            self._factor("equipment_condition", RiskCategory.EQUIPMENT_LOSS, equipment_score, "PredictiveEngine", "Worst asset condition"),
            self._factor("personnel_readiness", RiskCategory.PERSONNEL_CASUALTY, personnel_score, "ReadinessCalculator", "Unit readiness deficit"),
            self._factor("historical_loss", RiskCategory.MISSION_FAILURE, historical_loss, "AARGenerator", "Historical loss in similar scenarios"),
            self._factor("environmental_factors", RiskCategory.MISSION_FAILURE, env_score, "ScenarioEngine", "Weather/terrain constraints"),
            self._factor("mission_complexity", RiskCategory.MISSION_FAILURE, complexity_score, "MissionPlanner", "Objective/duration complexity"),
            self._factor("gps_comms_denial", RiskCategory.STRATEGIC_IMPACT, gps_score, "GPSMonitor", "EW denial probability"),
            self._factor("platform_type", RiskCategory.STRATEGIC_IMPACT, 0.2, "MissionPlanner", f"platform={mission.get('platform_type', 'air')}", weight=0.05),
        ]
        return self._build_assessment(context="mission", factors=factors, assets=assets)

    def assess_engagement(self, engagement_request: dict) -> RiskAssessment:
        """Assess engagement-specific risk for kill-chain execution gate."""
        collateral = str(engagement_request.get("collateral_estimate", "LOW")).upper()
        collateral_score = 0.9 if "UNACCEPTABLE" in collateral else (0.7 if "HIGH" in collateral else 0.3)
        confidence_score = 1.0 - float(engagement_request.get("confidence", 0.7))
        factors = [
            self._factor("engagement_collateral", RiskCategory.COLLATERAL_DAMAGE, collateral_score, "KillChain", "Collateral risk estimate", weight=0.35),
            self._factor("target_confidence_uncertainty", RiskCategory.MISSION_FAILURE, confidence_score, "KillChain", "Target confidence uncertainty", weight=0.25),
            self._factor("threat_environment", RiskCategory.STRATEGIC_IMPACT, 0.5, "ThreatManager", "Current threat pressure", weight=0.20),
            self._factor("asset_exposure", RiskCategory.EQUIPMENT_LOSS, 0.45, "ForceProtection", "Shooter platform exposure", weight=0.20),
        ]
        return self._build_assessment(context="engagement", factors=factors, assets=[{"type": "uav_quadrotor_small"}])

    def assess_patrol(self, route: List[tuple], assets: List[dict]) -> RiskAssessment:
        """Assess patrol route risk considering path length and exposure."""
        route_len = max(1, len(route))
        route_complexity = min(1.0, route_len / 20.0)
        factors = [
            self._factor("route_threat_overlay", RiskCategory.STRATEGIC_IMPACT, min(1.0, route_complexity + 0.2), "ThreatManager", "Threat overlays on patrol route"),
            self._factor("asset_condition", RiskCategory.EQUIPMENT_LOSS, max([a.get("condition_score", 0.3) for a in assets] or [0.3]), "PredictiveEngine", "Patrol asset health"),
            self._factor("mission_complexity", RiskCategory.MISSION_FAILURE, route_complexity, "PathPlanner", "Route waypoint density"),
        ]
        return self._build_assessment(context="patrol", factors=factors, assets=assets)

    def get_force_risk_dashboard(self) -> dict:
        """Aggregate force-wide risk posture for command dashboards."""
        assessments = list(self._assessments.values())
        by_level = {level.value: 0 for level in RiskLevel}
        for item in assessments:
            by_level[item.risk_level.value] += 1
        avg_score = sum(a.overall_score for a in assessments) / max(1, len(assessments))
        return {
            "total_assessments": len(assessments),
            "by_risk_level": by_level,
            "average_score": avg_score,
            "hotspots": [a.assessment_id for a in assessments if a.risk_level in {RiskLevel.RED, RiskLevel.BLACK}],
        }

    def get_risk_history(self, entity_id: str, days: int = 90) -> RiskProfile:
        """Return historical risk profile for a specific entity ID."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
        if entity_id not in self._history:
            history = []
            for item in self._assessments.values():
                if item.timestamp >= cutoff:
                    history.append({"timestamp": item.timestamp.isoformat(), "score": item.overall_score, "level": item.risk_level.value})
            self._history[entity_id] = RiskProfile(
                entity_id=entity_id,
                entity_type="unit",
                risk_history=history,
                cumulative_risk_exposure=sum(h["score"] for h in history),
                incidents=[h for h in history if h["level"] in {"red", "black"}],
            )
        return self._history[entity_id]
