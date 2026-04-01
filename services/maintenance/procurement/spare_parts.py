"""Spare parts inventory manager for maintenance readiness."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from services.maintenance.models import SparePartInventory


class SparePartsManager:
    """Track stock levels and reorder triggers for tactical sustainment."""

    def __init__(self):
        self.parts: Dict[str, SparePartInventory] = {}

    def add_part(
        self,
        part_name,
        part_number,
        quantity,
        reorder_threshold,
        reorder_quantity,
        unit_cost,
        location,
        compatible_assets,
    ) -> SparePartInventory:
        part = SparePartInventory(
            part_id=f"part-{uuid4().hex[:10]}",
            part_name=str(part_name),
            part_number=str(part_number),
            quantity_on_hand=int(quantity),
            reorder_threshold=int(reorder_threshold),
            reorder_quantity=int(reorder_quantity),
            unit_cost=float(unit_cost),
            location=str(location),
            compatible_assets=[str(a) for a in compatible_assets],
            last_restock=datetime.now(timezone.utc),
        )
        self.parts[part.part_id] = part
        return part

    def get_part(self, part_id) -> Optional[SparePartInventory]:
        return self.parts.get(part_id)

    def get_parts(self, compatible_asset_type=None) -> List[SparePartInventory]:
        rows = list(self.parts.values())
        if compatible_asset_type is None:
            return rows
        value = str(compatible_asset_type)
        return [part for part in rows if value in part.compatible_assets]

    def consume(self, part_id, quantity: int) -> bool:
        part = self.get_part(part_id)
        if part is None:
            return False
        qty = int(quantity)
        if qty < 0 or part.quantity_on_hand < qty:
            return False
        part.quantity_on_hand -= qty
        return True

    def restock(self, part_id, quantity: int):
        part = self.get_part(part_id)
        if part is None:
            raise KeyError(f"Part not found: {part_id}")
        part.quantity_on_hand += int(quantity)
        part.last_restock = datetime.now(timezone.utc)

    def check_reorder(self) -> List[SparePartInventory]:
        return [part for part in self.parts.values() if part.needs_reorder()]

    def get_inventory_value(self) -> float:
        return float(sum(part.quantity_on_hand * part.unit_cost for part in self.parts.values()))

    def get_stats(self) -> dict:
        low_stock = self.check_reorder()
        return {
            "total_parts": len(self.parts),
            "inventory_value": self.get_inventory_value(),
            "low_stock_count": len(low_stock),
        }

    def create_standard_inventory(self) -> List[SparePartInventory]:
        catalog = [
            ("Engine Turbine Blade", "ENG-TB-001", 24, 10, 30, 4200.0, "Depot-A", ["FIGHTER_JET", "HELICOPTER"]),
            ("Oil Filter", "OIL-FLT-002", 300, 120, 250, 45.0, "Depot-B", ["FIGHTER_JET", "TANK", "TRUCK"]),
            ("Brake Pad Set", "BRK-PAD-003", 180, 80, 120, 120.0, "Depot-B", ["TANK", "TRUCK", "APC"]),
            ("Radar Module", "RDR-MOD-004", 16, 6, 12, 8000.0, "Depot-C", ["RADAR_SYSTEM"]),
            ("Communication Board", "COM-BRD-005", 40, 15, 30, 1500.0, "Depot-C", ["COMM_SYSTEM", "RADAR_SYSTEM"]),
            ("Fuel Pump", "FUEL-PMP-006", 65, 25, 50, 900.0, "Depot-A", ["FIGHTER_JET", "HELICOPTER", "TRUCK"]),
            ("Run-Flat Tire", "TIRE-RF-007", 220, 90, 180, 350.0, "Depot-D", ["APC", "TANK", "TRUCK"]),
            ("Bearing Kit", "BRG-KIT-008", 140, 60, 120, 280.0, "Depot-A", ["FIGHTER_JET", "PATROL_BOAT"]),
            ("Seal Kit", "SEAL-KIT-009", 190, 70, 150, 95.0, "Depot-B", ["PATROL_BOAT", "HELICOPTER", "FIGHTER_JET"]),
            ("Sensor Array", "SNS-ARR-010", 28, 12, 20, 2600.0, "Depot-C", ["UAV", "RADAR_SYSTEM"]),
            ("Hydraulic Line", "HYD-LIN-011", 120, 50, 100, 210.0, "Depot-B", ["TANK", "APC"]),
            ("Avionics Fuse Pack", "AVN-FUSE-012", 320, 150, 250, 18.0, "Depot-A", ["FIGHTER_JET", "HELICOPTER", "UAV"]),
            ("Cooling Pump", "CLG-PMP-013", 72, 30, 60, 740.0, "Depot-C", ["RADAR_SYSTEM", "COMM_SYSTEM"]),
            ("Propulsion Nozzle", "PRP-NZL-014", 20, 8, 16, 5200.0, "Depot-A", ["FIGHTER_JET"]),
            ("Rotor Blade Segment", "RTR-BLD-015", 30, 10, 20, 3100.0, "Depot-A", ["HELICOPTER"]),
            ("Transmission Gear", "TRN-GEAR-016", 34, 14, 24, 1700.0, "Depot-D", ["TANK", "APC"]),
            ("Naval Intake Filter", "NVL-FLT-017", 48, 20, 36, 230.0, "Depot-E", ["PATROL_BOAT", "FRIGATE"]),
            ("Generator Alternator", "GEN-ALT-018", 52, 18, 30, 1300.0, "Depot-E", ["GENERATOR", "TRUCK"]),
            ("Control Actuator", "CTRL-ACT-019", 44, 16, 28, 2100.0, "Depot-C", ["FIGHTER_JET", "UAV", "RADAR_SYSTEM"]),
            ("Data Bus Coupler", "DBUS-CPL-020", 56, 22, 36, 480.0, "Depot-C", ["COMM_SYSTEM", "SENSOR_ARRAY"]),
        ]
        out = []
        for item in catalog:
            out.append(self.add_part(*item))
        return out
