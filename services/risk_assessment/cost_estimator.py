"""Cost estimator for expected loss in tactical mission risk assessment.

Military context:
Expected-loss calculations translate probability of asset loss into monetary
impact to support force planning and contingency budgeting decisions.
"""

from __future__ import annotations

from typing import Dict, List

from services.risk_assessment.models import RiskAssessment


class CostEstimator:
    """Estimate equipment and operational loss costs from risk outputs."""

    ASSET_COSTS = {
        "F-15SA": 100_000_000,
        "AH-64E_Apache": 35_000_000,
        "MQ-9_Reaper": 16_000_000,
        "M1A2_Abrams": 9_000_000,
        "LAV_25": 1_500_000,
        "patrol_boat": 5_000_000,
        "frigate": 800_000_000,
        "radar_system": 50_000_000,
        "comm_tower": 2_000_000,
        "uav_quadrotor_small": 50_000,
        "ugv_wheeled_small": 200_000,
        "usv_small": 500_000,
    }

    def __init__(self):
        self.cost_table: Dict[str, float] = dict(self.ASSET_COSTS)

    def estimate_equipment_cost(self, assets: List[dict], loss_probability: float) -> float:
        """Compute expected equipment loss cost from probability-weighted assets."""
        p = max(0.0, min(1.0, float(loss_probability)))
        total = 0.0
        for asset in assets:
            name = asset.get("type") or asset.get("name") or "uav_quadrotor_small"
            cost = float(self.cost_table.get(str(name), 250_000.0))
            total += cost * p
        return total

    def estimate_operational_cost(self, mission_duration_hours: float, platform_count: int) -> float:
        """Estimate baseline operational expenditure for mission execution."""
        duration = max(0.0, float(mission_duration_hours))
        count = max(0, int(platform_count))
        hourly_rate_per_platform = 2500.0
        return duration * count * hourly_rate_per_platform

    def estimate_total_risk_cost(self, assessment: RiskAssessment, assets: List[dict]) -> float:
        """Combine equipment and mission-failure operational costs."""
        eq = self.estimate_equipment_cost(assets, assessment.equipment_loss_prob)
        op = self.estimate_operational_cost(
            mission_duration_hours=max(1.0, assessment.mission_failure_prob * 10.0),
            platform_count=max(1, len(assets)),
        )
        return eq + (op * assessment.mission_failure_prob)
