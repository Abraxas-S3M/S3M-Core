"""Logistics digital twin wrapper for sustainment planning workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Sequence

from src.apps._shared import utc_now_iso
from src.apps.logistics import LogisticsModule


@dataclass
class SupplyChainTwin:
    """Thin twin around the logistics module for gap-closure integration."""

    module: LogisticsModule

    def __init__(self) -> None:
        self.module = LogisticsModule()

    def run_cycle(self, supply_records: Sequence[dict]) -> Dict[str, Any]:
        """Run one predictive + reporting cycle on validated supply records."""
        if not isinstance(supply_records, list):
            raise ValueError("supply_records must be a list of shipment dictionaries")
        prediction = self.module.predict(list(supply_records))
        return {
            "timestamp": utc_now_iso(),
            "prediction": prediction,
            "status": self.module.get_full_status(),
        }

    def predict_disruptions(self, supply_records: Sequence[dict]) -> Dict[str, Any]:
        """Predict sustainment disruptions for portal/API usage."""
        if not isinstance(supply_records, list):
            raise ValueError("supply_records must be a list of shipment dictionaries")
        return self.module.predict(list(supply_records))

    def health_check(self) -> Dict[str, Any]:
        """Return logistics twin readiness without requiring model weights."""
        health = self.module.health_check()
        health["twin"] = "supply_chain_twin"
        return health
