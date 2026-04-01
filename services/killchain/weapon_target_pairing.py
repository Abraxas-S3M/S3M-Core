"""Rule-based weapon-target pairing for tactical engagement selection.

Military context:
Pairing logic prioritizes mission effectiveness while controlling collateral
risk through deterministic suitability scoring under disconnected operations.
"""

from __future__ import annotations

from typing import List

from services.killchain.models import TargetClassification


class WeaponTargetPairing:
    """Select suitable weapon options for classified target types."""

    PAIRING_RULES = {
        "ENEMY_UAV": {"preferred": "air_to_air_missile", "alternative": "electronic_kill", "min_confidence": 0.7},
        "ENEMY_UGV": {"preferred": "anti_tank_guided", "alternative": "direct_fire", "min_confidence": 0.8},
        "ENEMY_SHIP": {"preferred": "anti_ship_missile", "alternative": "torpedo", "min_confidence": 0.8},
        "ENEMY_INFANTRY": {"preferred": "precision_munition", "alternative": "area_denial", "min_confidence": 0.9},
        "RADAR_SYSTEM": {"preferred": "anti_radiation_missile", "alternative": "standoff_munition", "min_confidence": 0.7},
    }

    def __init__(self):
        self.rules = dict(self.PAIRING_RULES)

    def pair(self, target: TargetClassification, available_weapons: List[dict]) -> dict:
        """Return best weapon candidate and suitability scoring rationale."""
        rule = self.rules.get(target.classification.upper())
        if not available_weapons:
            return {"weapon": None, "suitability_score": 0.0, "reasoning": "No available weapons"}

        def weapon_score(weapon: dict) -> float:
            score = 0.4
            w_type = str(weapon.get("type", "")).lower()
            w_range = float(weapon.get("range_m", 0.0))
            collateral_radius = float(weapon.get("collateral_radius_m", 1000.0))
            if rule:
                if w_type == rule["preferred"]:
                    score += 0.4
                elif w_type == rule["alternative"]:
                    score += 0.25
                if target.confidence >= float(rule.get("min_confidence", 0.5)):
                    score += 0.1
            if w_range >= 500.0:
                score += 0.05
            if collateral_radius <= max(10.0, target.civilian_proximity_m * 0.2):
                score += 0.05
            return max(0.0, min(1.0, score))

        best = max(available_weapons, key=weapon_score)
        score = weapon_score(best)
        return {
            "weapon": best,
            "suitability_score": score,
            "reasoning": f"Selected {best.get('type')} for {target.classification} with score {score:.2f}",
        }
