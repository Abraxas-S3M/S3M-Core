#!/usr/bin/env python3
"""Phase 17 full procurement and maintenance demo."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from random import random

from services.maintenance import AssetType, MaintenanceManager


def _simulate_aircraft_readings(cycle: int, degraded_temp: bool = False, vibration_spike: bool = False) -> dict:
    base_temp = 420 + cycle * 0.8
    base_vibration = 2.0 + cycle * 0.01
    if degraded_temp:
        base_temp += cycle * 0.9
    if vibration_spike and cycle > 50:
        base_vibration += 3.8
    return {
        "temperature_c": round(base_temp + random() * 3.0, 2),
        "vibration_g": round(base_vibration + random() * 0.2, 3),
        "pressure_psi": round(35.0 - cycle * 0.03 + random() * 0.2, 3),
        "rpm": round(12000 + cycle * 4 + random() * 30, 2),
        "oil_temp_c": round(92 + cycle * 0.15 + random() * 0.8, 2),
        "fuel_flow_rate": round(0.78 + cycle * 0.0005 + random() * 0.01, 4),
    }


def main() -> None:
    manager = MaintenanceManager()
    assets = manager.asset_registry.create_saudi_fleet_template()
    parts = manager.spare_parts.create_standard_inventory()
    print(f"Template assets loaded: {len(assets)}")
    print(f"Standard spare parts loaded: {len(parts)}")

    aircraft = [
        a
        for a in assets
        if a.asset_type in {AssetType.AIRCRAFT, AssetType.FIGHTER_JET, AssetType.HELICOPTER, AssetType.UAV}
    ][:6]

    for idx, asset in enumerate(aircraft):
        for cycle in range(100):
            readings = _simulate_aircraft_readings(
                cycle=cycle,
                degraded_temp=(idx == 4),
                vibration_spike=(idx == 5),
            )
            manager.ingest_telemetry(asset.asset_id, readings, operating_mode="cruise")

    print("\nRUL predictions:")
    for asset in aircraft:
        pred = manager.predict_rul(asset.asset_id)
        print(f"- {asset.designation}: RUL={pred.rul_hours:.1f}h risk={pred.risk_level} confidence={pred.confidence:.2f}")

    print("\nCondition alerts for degraded aircraft:")
    for asset in aircraft[-2:]:
        hist = manager.fleet_manager.telemetry_history.get(asset.asset_id, [])
        latest = manager.predictive_engine.condition_monitor.evaluate(hist[-1]) if hist else {}
        print(f"- {asset.designation}: alerts={len(latest.get('alerts', []))} condition={latest.get('condition')}")

    work_orders = manager.generate_work_orders()
    print(f"\nGenerated work orders: {len(work_orders)}")
    for wo in work_orders[:10]:
        print(f"- {wo.priority.value}: {wo.title} ({wo.asset_id})")

    procurement = manager.check_procurement_needs()
    print(f"\nProcurement requests generated: {len(procurement)}")
    for req in procurement[:10]:
        print(f"- {req.part_name} x{req.quantity} [{req.status.value}]")

    readiness = manager.fleet_manager.get_fleet_readiness()
    print("\nFleet readiness:", readiness)
    print("\nFleet report:\n")
    print(manager.generate_fleet_report())

    summary = manager.asset_registry.get_fleet_summary()
    print("\nFleet summary:")
    print(
        f"total={summary['total']} operational={readiness['operational']} "
        f"critical={summary['critical_count']} maintenance_due={summary['maintenance_due_count']}"
    )


if __name__ == "__main__":
    main()
