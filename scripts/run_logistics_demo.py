#!/usr/bin/env python3
"""Phase 11 logistics demo for disruption, inventory, and routing."""

from __future__ import annotations

import os
import sys
from pprint import pprint

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.apps.logistics import LogisticsModule


def main() -> None:
    module = LogisticsModule()

    # 1) Add inventory items
    item_ids = [
        module.inventory_tracker.add_item("5.56mm Ammunition", "ammunition", 1200, "Depot-A", 800, "rounds"),
        module.inventory_tracker.add_item("JP-8 Fuel", "fuel", 5000, "Depot-A", 3000, "liters"),
        module.inventory_tracker.add_item("Water", "sustainment", 2400, "Depot-B", 1500, "liters"),
        module.inventory_tracker.add_item("Medical Kits", "medical", 80, "Depot-B", 60, "kits"),
        module.inventory_tracker.add_item("Rations", "sustainment", 900, "Depot-C", 600, "packs"),
        module.inventory_tracker.add_item("Batteries", "electronics", 300, "Depot-C", 250, "units"),
        module.inventory_tracker.add_item("Spare Parts", "maintenance", 110, "Depot-A", 100, "units"),
        module.inventory_tracker.add_item("Comms Equipment", "electronics", 45, "Depot-B", 40, "units"),
        module.inventory_tracker.add_item("Body Armor", "protection", 220, "Depot-C", 180, "sets"),
        module.inventory_tracker.add_item("Night Vision", "optics", 35, "Depot-A", 30, "units"),
    ]

    # 2) Deplete some below thresholds
    module.inventory_tracker.update_quantity(item_ids[0], -600)
    module.inventory_tracker.update_quantity(item_ids[3], -30)
    module.inventory_tracker.update_quantity(item_ids[5], -90)

    # 3) Restock check
    restock = module.check_inventory()
    print("=== Restock Check ===")
    pprint(restock)

    # 4) Supply data with anomalies
    supply_data = [
        {"id": "SHP-100", "origin": "Depot-A", "dest": "FOB-North", "delay_hours": 2, "weight": 800, "priority": 5, "route_distance": 120},
        {"id": "SHP-101", "origin": "Depot-B", "dest": "FOB-East", "delay_hours": 14, "weight": 1500, "priority": 9, "route_distance": 340},
        {"id": "SHP-102", "origin": "Depot-C", "dest": "FOB-West", "delay_hours": 1, "weight": 500, "priority": 3, "route_distance": 90},
        {"id": "SHP-103", "origin": "Depot-A", "dest": "FOB-South", "delay_hours": 18, "weight": 1700, "priority": 10, "route_distance": 410},
    ]
    prediction = module.predict(supply_data)
    print("\n=== Disruption Prediction ===")
    pprint(prediction)

    # 5) Route optimization
    threats = [
        {"id": "T-1", "position": (350, 160, 0), "level": "MEDIUM"},
        {"id": "T-2", "position": (620, 320, 0), "level": "HIGH"},
        {"id": "T-3", "position": (760, 420, 0), "level": "CRITICAL"},
    ]
    route = module.optimize_route(origin=(0, 0, 0), dest=(1000, 500, 0), threats=threats)
    print("\n=== Route Optimization ===")
    pprint(route)


if __name__ == "__main__":
    main()
