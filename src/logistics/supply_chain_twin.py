"""
S3M Supply Chain Digital Twin - Gap 3 of 7.

Depot to consumer flow model with PPO-based reorder optimization.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("s3m.logistics.twin")


class SupplyStatus(str, Enum):
    CRITICAL = "CRITICAL"  # < 10 % stock
    LOW = "LOW"  # 10-30 %
    ADEQUATE = "ADEQUATE"  # 30-80 %
    SURPLUS = "SURPLUS"  # > 80 %


@dataclass
class InventoryItem:
    item_id: str
    name_en: str
    name_ar: str
    unit: str
    quantity: float
    min_threshold: float  # reorder point
    max_capacity: float
    lead_time_days: float  # replenishment lag
    daily_consumption_rate: float
    cost_per_unit: float = 0.0
    category: str = "general"

    @property
    def status(self) -> SupplyStatus:
        pct = self.quantity / self.max_capacity if self.max_capacity > 0 else 0
        if pct < 0.10:
            return SupplyStatus.CRITICAL
        if pct < 0.30:
            return SupplyStatus.LOW
        if pct < 0.80:
            return SupplyStatus.ADEQUATE
        return SupplyStatus.SURPLUS

    @property
    def days_remaining(self) -> float:
        if self.daily_consumption_rate <= 0:
            return float("inf")
        return self.quantity / self.daily_consumption_rate


@dataclass
class Depot:
    depot_id: str
    name: str
    lat: float
    lon: float
    inventory: Dict[str, InventoryItem] = field(default_factory=dict)

    def add_item(self, item: InventoryItem) -> None:
        self.inventory[item.item_id] = item

    def consume(self, item_id: str, qty: float) -> Tuple[bool, float]:
        item = self.inventory.get(item_id)
        if not item:
            return False, 0.0
        consumed = min(qty, item.quantity)
        item.quantity -= consumed
        return True, consumed

    def restock(self, item_id: str, qty: float) -> bool:
        item = self.inventory.get(item_id)
        if not item:
            return False
        item.quantity = min(item.quantity + qty, item.max_capacity)
        return True

    def critical_items(self) -> List[InventoryItem]:
        return [
            i
            for i in self.inventory.values()
            if i.status in (SupplyStatus.CRITICAL, SupplyStatus.LOW)
        ]


class PPOReorderAgent:
    """
    PPO-backed reorder quantity decisions.

    State vector:
      [stock_pct, demand_pressure, threshold_pct, lead_time_pressure, days_remaining_norm]
    Action index:
      reorder fraction in {0%, 25%, 50%, 75%, 100%} of max capacity
    """

    ACTIONS = [0.0, 0.25, 0.50, 0.75, 1.0]

    def __init__(self, model: Optional[Any] = None, deterministic: bool = True) -> None:
        self._model = model
        self._deterministic = deterministic

    @property
    def model_loaded(self) -> bool:
        return self._model is not None

    def set_model(self, model: Any) -> None:
        self._model = model

    def load_model(self, model_path: str) -> bool:
        """Load a serialized stable-baselines3 PPO model."""
        try:
            from stable_baselines3 import PPO  # type: ignore

            self._model = PPO.load(model_path)
            return True
        except Exception as exc:  # pragma: no cover - import/runtime dependent
            logger.warning("Failed to load PPO reorder model '%s': %s", model_path, exc)
            self._model = None
            return False

    def _state_vector(self, item: InventoryItem) -> List[float]:
        max_capacity = max(item.max_capacity, 1.0)
        stock_pct = max(0.0, min(item.quantity / max_capacity, 1.0))
        threshold_pct = max(0.0, min(item.min_threshold / max_capacity, 1.0))

        baseline_daily = max_capacity / 30.0
        demand_pressure = max(0.0, min(item.daily_consumption_rate / max(baseline_daily, 1e-6), 2.0))
        lead_time_pressure = max(
            0.0,
            min((item.daily_consumption_rate * max(item.lead_time_days, 0.0)) / max_capacity, 2.0),
        )
        days_remaining = item.days_remaining if item.days_remaining != float("inf") else 365.0
        days_remaining_norm = max(0.0, min(days_remaining / 30.0, 2.0))

        return [
            stock_pct,
            demand_pressure,
            threshold_pct,
            lead_time_pressure,
            days_remaining_norm,
        ]

    def _nearest_action_idx(self, fraction: float) -> int:
        clipped = max(0.0, min(fraction, 1.0))
        return min(range(len(self.ACTIONS)), key=lambda i: abs(self.ACTIONS[i] - clipped))

    def _fallback_action_idx(self, item: InventoryItem) -> int:
        # Tactical continuity fallback: bias toward pre-positioning stock for lead-time gaps.
        max_capacity = max(item.max_capacity, 1.0)
        projected_lead_time_need = item.daily_consumption_rate * max(item.lead_time_days, 1.0)
        target_stock = min(max_capacity, max(item.min_threshold, projected_lead_time_need))
        shortfall = max(0.0, target_stock - item.quantity)
        return self._nearest_action_idx(shortfall / max_capacity)

    def recommend_reorder(self, item: InventoryItem) -> float:
        """Returns recommended reorder quantity."""
        if item.max_capacity <= 0:
            return 0.0

        action_idx: Optional[int] = None
        if self._model is not None:
            try:
                obs = self._state_vector(item)
                predicted, _ = self._model.predict(obs, deterministic=self._deterministic)
                action_idx = int(predicted)
            except Exception as exc:
                logger.warning(
                    "PPO reorder inference failed for item '%s'; using fallback policy: %s",
                    item.item_id,
                    exc,
                )

        if action_idx is None:
            action_idx = self._fallback_action_idx(item)

        action_idx = max(0, min(action_idx, len(self.ACTIONS) - 1))
        return self.ACTIONS[action_idx] * item.max_capacity


class SupplyChainTwin:
    """
    Models the full depot network.

    Usage:
        twin = SupplyChainTwin()
        twin.add_depot(depot)
        twin.step(days=1)                   # advance simulation
        alerts = twin.generate_alerts()
        plan = twin.optimize_reorders()
    """

    def __init__(self, reorder_agent: Optional[PPOReorderAgent] = None) -> None:
        self._depots: Dict[str, Depot] = {}
        self._agent = reorder_agent or PPOReorderAgent()
        self._day = 0.0

    def add_depot(self, depot: Depot) -> None:
        self._depots[depot.depot_id] = depot

    def step(self, days: float = 1.0) -> None:
        """Advance the twin by `days` simulation days."""
        self._day += days
        for depot in self._depots.values():
            for item in depot.inventory.values():
                consumed = item.daily_consumption_rate * days
                # Tactical realism: local operations tempo introduces +/-10% draw variability.
                consumed *= 1 + random.uniform(-0.1, 0.1)
                depot.consume(item.item_id, consumed)

    def generate_alerts(self) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        for depot in self._depots.values():
            for item in depot.critical_items():
                alerts.append(
                    {
                        "depot_id": depot.depot_id,
                        "item_id": item.item_id,
                        "name_en": item.name_en,
                        "name_ar": item.name_ar,
                        "status": item.status.value,
                        "quantity": item.quantity,
                        "days_left": round(item.days_remaining, 1),
                        "severity": "HIGH" if item.status == SupplyStatus.CRITICAL else "MEDIUM",
                    }
                )
        return sorted(alerts, key=lambda a: a["days_left"])

    def optimize_reorders(self) -> List[Dict[str, Any]]:
        """Use PPO agent to recommend reorder quantities per item per depot."""
        orders: List[Dict[str, Any]] = []
        for depot in self._depots.values():
            for item in depot.inventory.values():
                qty = self._agent.recommend_reorder(item)
                if qty > 0:
                    orders.append(
                        {
                            "depot_id": depot.depot_id,
                            "item_id": item.item_id,
                            "name_en": item.name_en,
                            "name_ar": item.name_ar,
                            "reorder_qty": round(qty, 1),
                            "cost_estimate": round(qty * item.cost_per_unit, 2),
                            "lead_time_days": item.lead_time_days,
                            "priority": item.status.value,
                        }
                    )
        return orders

    def full_status(self) -> Dict[str, Any]:
        return {
            "sim_day": self._day,
            "depots": {
                did: {
                    "name": d.name,
                    "inventory": {
                        iid: {
                            "quantity": i.quantity,
                            "status": i.status.value,
                            "days_remaining": round(i.days_remaining, 1),
                        }
                        for iid, i in d.inventory.items()
                    },
                }
                for did, d in self._depots.items()
            },
            "alerts": self.generate_alerts(),
        }

    def get_status(self) -> Dict[str, Any]:
        """
        Return current supply twin status for GUI adapters.

        Tactical context: exposing a stable status method keeps sustainment
        workspaces operational even when upstream interfaces vary by deployment.
        """

        return self.full_status()

    def predict_disruptions(self, supply_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compatibility API for portal-level sustainment prediction.

        Tactical context: this lightweight heuristic keeps logistics triage
        available in air-gapped deployments when heavier analytics are absent.
        """
        if not isinstance(supply_records, list):
            raise ValueError("supply_records must be a list")

        disruptions: List[Dict[str, Any]] = []
        for idx, record in enumerate(supply_records):
            if not isinstance(record, dict):
                continue
            shipment_id = str(record.get("id", f"shipment-{idx+1}"))
            delay_hours = float(record.get("delay_hours", 0.0))
            priority = float(record.get("priority", 1.0))
            route_distance = float(record.get("route_distance", 0.0))
            is_disrupted = delay_hours >= 12.0 or (delay_hours >= 4.0 and priority >= 8.0)
            if not is_disrupted:
                continue
            disruptions.append(
                {
                    "shipment_id": shipment_id,
                    "anomaly_score": round(min(1.0, max(0.0, delay_hours / 24.0)), 3),
                    "analysis": (
                        f"Delay={delay_hours:.1f}h, priority={priority:.0f}, "
                        f"route_distance={route_distance:.1f}km indicates sustainment risk."
                    ),
                    "recommended_action": "Reroute convoy and prioritize escort for critical shipments",
                }
            )

        total = len([r for r in supply_records if isinstance(r, dict)])
        ratio = (len(disruptions) / total) if total else 0.0
        overall_risk = "LOW"
        if ratio >= 0.35:
            overall_risk = "HIGH"
        elif ratio >= 0.15:
            overall_risk = "MEDIUM"

        return {
            "total_shipments": total,
            "anomalies_detected": len(disruptions),
            "disruptions": disruptions,
            "overall_risk": overall_risk,
        }

    def run_cycle(self, supply_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compatibility wrapper returning prediction + twin status payload."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prediction": self.predict_disruptions(supply_records),
            "status": self.full_status(),
        }

    def health_check(self) -> Dict[str, Any]:
        """Compatibility health payload used by integrated portal routes."""
        return {
            "status": "operational",
            "component": "supply_chain_twin",
            "depots": len(self._depots),
            "model_loaded": self._agent.model_loaded,
        }
