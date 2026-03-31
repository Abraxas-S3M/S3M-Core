"""Phase 11 logistics orchestration module."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from src.apps._shared import utc_now_iso
from src.apps.logistics.convoy_route_optimizer import ConvoyRouteOptimizer
from src.apps.logistics.inventory_tracker import InventoryTracker
from src.apps.logistics.supply_chain_predictor import SupplyChainPredictor


class LogisticsModule:
    """Orchestrate supply disruption, route, and inventory functions."""

    def __init__(self) -> None:
        self.predictor = SupplyChainPredictor()
        self.route_optimizer = ConvoyRouteOptimizer()
        self.inventory_tracker = InventoryTracker()
        self._last_prediction: Optional[dict] = None
        self._routes: List[dict] = []

    def predict(self, supply_data: Sequence[dict]) -> dict:
        self._last_prediction = self.predictor.predict_disruptions(list(supply_data))
        return self._last_prediction

    def optimize_route(self, origin: tuple, dest: tuple, threats: Optional[List[dict]] = None) -> dict:
        route = self.route_optimizer.optimize_route(origin=origin, destination=dest, threat_overlay=threats)
        self._routes.append(route)
        if len(self._routes) > 100:
            self._routes = self._routes[-100:]
        return route

    def check_inventory(self) -> List[dict]:
        return self.inventory_tracker.check_restock()

    def generate_report(self) -> str:
        report = self.inventory_tracker.generate_supply_report()
        disruption = self._last_prediction or {"overall_risk": "UNKNOWN", "anomalies_detected": 0}
        return (
            f"Logistics status ({utc_now_iso()}):\n"
            f"- Supply disruption risk: {disruption.get('overall_risk')}\n"
            f"- Anomalies detected: {disruption.get('anomalies_detected')}\n\n"
            f"{report}"
        )

    def get_full_status(self) -> dict:
        return {
            "timestamp": utc_now_iso(),
            "inventory": self.inventory_tracker.get_stats(),
            "active_routes": len(self._routes),
            "last_route": self._routes[-1] if self._routes else None,
            "disruption_prediction": self._last_prediction,
        }

    def health_check(self) -> dict:
        return {
            "status": "operational",
            "predictor": "ready",
            "route_optimizer": "ready",
            "inventory_tracker": "ready",
            "routes_cached": len(self._routes),
        }
