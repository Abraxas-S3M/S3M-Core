"""Inventory tracking for tactical logistics readiness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.apps._shared import ensure_non_empty_text, summarize_counts, utc_now_iso
from src.llm_core.engine_registry import TaskDomain
from src.llm_core.orchestrator import Orchestrator, QueryRequest


class InventoryTracker:
    """In-memory inventory with military restock monitoring."""

    def __init__(self) -> None:
        self.inventory: Dict[str, dict] = {}
        self.orchestrator = Orchestrator()

    def add_item(
        self,
        name: str,
        category: str,
        quantity: int,
        location: str,
        reorder_threshold: int,
        unit: str = "units",
    ) -> str:
        name = ensure_non_empty_text(name, "name")
        category = ensure_non_empty_text(category, "category")
        location = ensure_non_empty_text(location, "location")
        unit = ensure_non_empty_text(unit, "unit")
        if not isinstance(quantity, int) or quantity < 0:
            raise ValueError("quantity must be a non-negative integer")
        if not isinstance(reorder_threshold, int) or reorder_threshold < 0:
            raise ValueError("reorder_threshold must be a non-negative integer")
        item_id = f"item-{uuid4().hex[:12]}"
        self.inventory[item_id] = {
            "item_id": item_id,
            "name": name,
            "category": category,
            "quantity": quantity,
            "location": location,
            "reorder_threshold": reorder_threshold,
            "unit": unit,
            "last_updated": utc_now_iso(),
        }
        return item_id

    def update_quantity(self, item_id: str, delta: int) -> None:
        if item_id not in self.inventory:
            raise ValueError(f"Unknown item_id: {item_id}")
        if not isinstance(delta, int):
            raise ValueError("delta must be an integer")
        current = self.inventory[item_id]["quantity"]
        self.inventory[item_id]["quantity"] = max(0, current + delta)
        self.inventory[item_id]["last_updated"] = utc_now_iso()

    def get_inventory(self, category: str = None, location: str = None) -> List[dict]:
        out = list(self.inventory.values())
        if category:
            out = [row for row in out if row.get("category") == category]
        if location:
            out = [row for row in out if row.get("location") == location]
        return out

    def check_restock(self) -> List[dict]:
        restock: List[dict] = []
        for item in self.inventory.values():
            quantity = int(item.get("quantity", 0))
            threshold = int(item.get("reorder_threshold", 0))
            if quantity <= threshold:
                payload = dict(item)
                payload["shortfall"] = max(0, threshold - quantity)
                restock.append(payload)
        return restock

    def _inventory_summary(self) -> str:
        items = list(self.inventory.values())
        if not items:
            return "No inventory items recorded."
        by_category = summarize_counts(items, "category")
        low_items = self.check_restock()
        return (
            f"Total items: {len(items)}; by_category: {by_category}; "
            f"below_threshold: {len(low_items)}"
        )

    def _template_report(self) -> str:
        low = self.check_restock()
        if not low:
            return (
                "Military Supply Status Report:\n"
                "1) Critical shortages: none\n"
                "2) Restock priorities: maintain routine replenishment cycle\n"
                "3) Logistic recommendations: continue daily stock reconciliation."
            )
        top = ", ".join(item["name"] for item in low[:5])
        return (
            "Military Supply Status Report:\n"
            f"1) Critical shortages: {top}\n"
            "2) Restock priorities: prioritize ammunition/fuel/medical categories first\n"
            "3) Logistic recommendations: trigger immediate resupply convoy for listed items."
        )

    def generate_supply_report(self) -> str:
        summary = self._inventory_summary()
        prompt = (
            "Generate a military supply status report for this inventory: "
            f"{summary}. Include: 1) Critical shortages 2) Restock priorities "
            "3) Logistic recommendations."
        )
        try:
            response = self.orchestrator.process(QueryRequest(prompt=prompt, domain=TaskDomain.PLANNING))
            text = getattr(response, "text", "").strip()
            if text and "pending" not in text.lower():
                return text
        except Exception:
            pass
        return self._template_report()

    def get_stats(self) -> dict:
        items = list(self.inventory.values())
        return {
            "total_items": len(items),
            "by_category": summarize_counts(items, "category"),
            "items_below_threshold": len(self.check_restock()),
            "total_quantity": sum(int(item.get("quantity", 0)) for item in items),
        }

    def export(self, filepath: str) -> None:
        filepath = ensure_non_empty_text(filepath, "filepath")
        path = Path(filepath)
        if path.parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "timestamp": utc_now_iso(),
            "inventory": list(self.inventory.values()),
            "stats": self.get_stats(),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
