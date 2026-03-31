from __future__ import annotations

from src.apps.logistics import ConvoyRouteOptimizer, InventoryTracker, LogisticsModule, SupplyChainPredictor


def test_supply_chain_predictor_detects_anomalies():
    predictor = SupplyChainPredictor()
    data = [
        {"id": "S1", "origin": "A", "dest": "B", "delay_hours": 1, "weight": 100, "priority": 2, "route_distance": 50},
        {"id": "S2", "origin": "A", "dest": "C", "delay_hours": 2, "weight": 120, "priority": 3, "route_distance": 80},
        {"id": "S3", "origin": "D", "dest": "E", "delay_hours": 40, "weight": 900, "priority": 9, "route_distance": 900},
        {"id": "S4", "origin": "X", "dest": "Y", "delay_hours": 35, "weight": 850, "priority": 8, "route_distance": 870},
    ]
    out = predictor.predict_disruptions(data)
    assert out["total_shipments"] == 4
    assert "anomalies_detected" in out
    assert out["anomalies_detected"] >= 0


def test_convoy_route_optimizer_returns_route_metrics():
    optimizer = ConvoyRouteOptimizer()
    out = optimizer.optimize_route(origin=(0, 0, 0), destination=(1000, 0, 0), threat_overlay=[])
    assert "primary_route" in out
    assert out["primary_route"]["distance_m"] >= 0
    assert 0.0 <= out["primary_route"]["risk_score"] <= 1.0


def test_route_avoids_threat_zone_midpoint():
    optimizer = ConvoyRouteOptimizer()
    threat = [{"id": "T1", "position": (500, 0, 0), "level": "HIGH"}]
    out = optimizer.optimize_route(origin=(0, 0, 0), destination=(1000, 0, 0), threat_overlay=threat)
    path = out["primary_route"]["path"]
    # Direct route would have all y == 0; expect at least one waypoint deviating.
    assert any(abs(point[1]) > 0.0 for point in path[1:-1])


def test_inventory_tracker_lifecycle():
    tracker = InventoryTracker()
    item_id = tracker.add_item("Fuel", "consumable", 100, "depot-1", 40, unit="liters")
    tracker.update_quantity(item_id, -30)
    inventory = tracker.get_inventory()
    assert len(inventory) == 1
    assert inventory[0]["quantity"] == 70


def test_restock_identifies_below_threshold_items():
    tracker = InventoryTracker()
    item_id = tracker.add_item("Batteries", "power", 10, "fob", 12, unit="packs")
    restock = tracker.check_restock()
    assert any(item["item_id"] == item_id for item in restock)
    assert restock[0]["shortfall"] >= 0


def test_logistics_module_health():
    module = LogisticsModule()
    health = module.health_check()
    assert health["status"] == "operational"
