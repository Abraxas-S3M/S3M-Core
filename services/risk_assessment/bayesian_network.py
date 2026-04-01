"""Bayesian risk network for multi-factor mission risk computation.

Military context:
The network fuses threat, readiness, sustainment, environment, and EW evidence
to forecast casualty and equipment loss risk before mission execution.
"""

from __future__ import annotations

from typing import List

from services.risk_assessment.models import RiskCategory, RiskFactor, RiskLevel


class BayesianRiskNetwork:
    """Compute mission risk probabilities from weighted evidence factors."""

    CPT_THREAT_EQUIPMENT = {
        ("low", "excellent"): 0.02,
        ("low", "good"): 0.05,
        ("low", "fair"): 0.10,
        ("low", "poor"): 0.20,
        ("medium", "excellent"): 0.08,
        ("medium", "good"): 0.15,
        ("medium", "fair"): 0.30,
        ("medium", "poor"): 0.50,
        ("high", "excellent"): 0.20,
        ("high", "good"): 0.35,
        ("high", "fair"): 0.55,
        ("high", "poor"): 0.75,
        ("critical", "excellent"): 0.40,
        ("critical", "good"): 0.55,
        ("critical", "fair"): 0.75,
        ("critical", "poor"): 0.90,
    }

    CPT_THREAT_PERSONNEL = {
        ("low", "high_readiness"): 0.02,
        ("medium", "high_readiness"): 0.10,
        ("high", "high_readiness"): 0.25,
        ("critical", "high_readiness"): 0.45,
        ("low", "low_readiness"): 0.08,
        ("medium", "low_readiness"): 0.25,
        ("high", "low_readiness"): 0.50,
        ("critical", "low_readiness"): 0.80,
    }

    CPT_GPS_PLATFORM = {
        ("low", "air"): 0.05,
        ("medium", "air"): 0.15,
        ("high", "air"): 0.30,
        ("critical", "air"): 0.50,
        ("low", "ground"): 0.03,
        ("medium", "ground"): 0.10,
        ("high", "ground"): 0.22,
        ("critical", "ground"): 0.40,
        ("low", "maritime"): 0.04,
        ("medium", "maritime"): 0.12,
        ("high", "maritime"): 0.28,
        ("critical", "maritime"): 0.45,
    }

    def __init__(self):
        self.initialized = True

    @staticmethod
    def _to_level(score: float) -> str:
        if score < 0.25:
            return "low"
        if score < 0.5:
            return "medium"
        if score < 0.75:
            return "high"
        return "critical"

    @staticmethod
    def _equipment_condition(score: float) -> str:
        if score < 0.2:
            return "excellent"
        if score < 0.4:
            return "good"
        if score < 0.7:
            return "fair"
        return "poor"

    @staticmethod
    def _readiness_band(score: float) -> str:
        return "high_readiness" if score < 0.4 else "low_readiness"

    def _pick_factor(self, factors: List[RiskFactor], category: RiskCategory, fallback: float = 0.3) -> RiskFactor:
        same = [f for f in factors if f.category == category]
        if not same:
            return RiskFactor(
                factor_id=f"fallback-{category.value}",
                name=f"fallback_{category.value}",
                category=category,
                weight=0.2,
                score=fallback,
                confidence=0.5,
                source="fallback",
                detail="Fallback risk factor",
                mitigations=["Collect live data"],
            )
        return max(same, key=lambda f: f.weight * f.score)

    def compute(self, factors: List[RiskFactor]) -> dict:
        """Compute category probabilities and aggregate mission risk score."""
        threat = self._pick_factor(factors, RiskCategory.STRATEGIC_IMPACT, fallback=0.4)
        equipment = self._pick_factor(factors, RiskCategory.EQUIPMENT_LOSS, fallback=0.3)
        personnel = self._pick_factor(factors, RiskCategory.PERSONNEL_CASUALTY, fallback=0.3)
        mission = self._pick_factor(factors, RiskCategory.MISSION_FAILURE, fallback=0.3)

        threat_level = self._to_level(threat.score)
        equip_cond = self._equipment_condition(equipment.score)
        readiness_band = self._readiness_band(personnel.score)

        equipment_loss_prob = self.CPT_THREAT_EQUIPMENT[(threat_level, equip_cond)]
        personnel_loss_prob = self.CPT_THREAT_PERSONNEL[(threat_level, readiness_band)]

        gps_factor = next((f for f in factors if "gps" in f.name.lower() or "comms" in f.name.lower()), None)
        gps_level = self._to_level(gps_factor.score if gps_factor else 0.3)
        platform_type = "air"
        platform_hint = next((f for f in factors if "platform" in f.name.lower()), None)
        if platform_hint:
            text = platform_hint.detail.lower()
            if "ground" in text:
                platform_type = "ground"
            elif "maritime" in text or "sea" in text:
                platform_type = "maritime"
        mission_failure_prob = max(
            mission.score,
            self.CPT_GPS_PLATFORM[(gps_level, platform_type)] * 0.8 + 0.2 * mission.score,
        )

        # Interaction terms: poor equipment under high threat compounds loss.
        interaction_effects: List[dict] = []
        interaction_mult = 1.0
        if threat_level in {"high", "critical"} and equip_cond in {"fair", "poor"}:
            interaction_mult *= 1.20
            interaction_effects.append({"factor": "threat_x_equipment", "multiplier": 1.20})
        if readiness_band == "high_readiness" and threat_level in {"high", "critical"}:
            interaction_mult *= 0.90
            interaction_effects.append({"factor": "training_compensation", "multiplier": 0.90})

        equipment_loss_prob = min(1.0, equipment_loss_prob * interaction_mult)
        personnel_loss_prob = min(1.0, personnel_loss_prob * interaction_mult)
        mission_failure_prob = min(1.0, mission_failure_prob * interaction_mult)

        min_conf = min([f.confidence for f in factors], default=0.5)
        uncertainty_premium = (1.0 - min_conf) * 0.10
        equipment_loss_prob = min(1.0, equipment_loss_prob + uncertainty_premium)
        personnel_loss_prob = min(1.0, personnel_loss_prob + uncertainty_premium)
        mission_failure_prob = min(1.0, mission_failure_prob + uncertainty_premium)

        cost_estimate = (
            equipment_loss_prob * 3_000_000.0 + mission_failure_prob * 750_000.0 + personnel_loss_prob * 1_200_000.0
        )

        overall = (equipment_loss_prob * 0.35 + personnel_loss_prob * 0.35 + mission_failure_prob * 0.30) * 100.0

        if overall < 25:
            level = RiskLevel.GREEN
        elif overall < 50:
            level = RiskLevel.AMBER
        elif overall < 75:
            level = RiskLevel.RED
        else:
            level = RiskLevel.BLACK

        return {
            "equipment_loss_probability": equipment_loss_prob,
            "personnel_casualty_probability": personnel_loss_prob,
            "mission_failure_probability": mission_failure_prob,
            "cost_estimate_usd": cost_estimate,
            "overall_score": overall,
            "risk_level": level,
            "interaction_effects": interaction_effects,
            "uncertainty_premium": uncertainty_premium,
        }
