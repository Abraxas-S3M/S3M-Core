"""Asset registry for military lifecycle and maintenance state tracking."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

import yaml

from services.maintenance.models import (
    Asset,
    AssetCondition,
    AssetStatus,
    AssetType,
    MaintenanceRecord,
)


class AssetRegistry:
    """In-memory registry optimized for tactical fleet maintenance operations."""

    def __init__(self, max_assets: int = 50000):
        self.max_assets = int(max_assets)
        self.assets: Dict[str, Asset] = {}
        self.by_designation: Dict[str, str] = {}
        self.maintenance_records: Dict[str, List[MaintenanceRecord]] = {}
        self._config = self._load_config()

    def _load_config(self) -> dict:
        path = Path("configs/maintenance.yaml")
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                return {}
        return {}

    def _interval_days(self, asset_type: AssetType) -> int:
        intervals = (
            self._config.get("assets", {})
            .get("default_maintenance_interval_days", {})
        )
        if asset_type in {AssetType.AIRCRAFT, AssetType.FIGHTER_JET, AssetType.HELICOPTER, AssetType.TRANSPORT_AIRCRAFT, AssetType.UAV}:
            return int(intervals.get("aircraft", 90))
        if asset_type in {AssetType.GROUND_VEHICLE, AssetType.APC, AssetType.TANK, AssetType.TRUCK}:
            return int(intervals.get("vehicle", 180))
        if asset_type in {AssetType.NAVAL_VESSEL, AssetType.PATROL_BOAT, AssetType.FRIGATE}:
            return int(intervals.get("naval", 120))
        if asset_type == AssetType.RADAR_SYSTEM:
            return int(intervals.get("radar", 365))
        if asset_type == AssetType.COMM_SYSTEM:
            return int(intervals.get("comm", 180))
        return 180

    def register(
        self,
        name,
        designation,
        asset_type,
        serial_number,
        manufacturer,
        model,
        location,
        assigned_unit,
        operating_hours=0,
    ) -> Asset:
        if len(self.assets) >= self.max_assets:
            raise ValueError("Asset registry capacity exceeded")

        asset_id = f"ast-{uuid4().hex[:10]}"
        now = datetime.now(timezone.utc)
        interval_days = self._interval_days(AssetType(asset_type))
        asset = Asset(
            asset_id=asset_id,
            name=str(name),
            designation=str(designation),
            asset_type=AssetType(asset_type),
            status=AssetStatus.OPERATIONAL,
            condition=AssetCondition.GOOD,
            serial_number=str(serial_number),
            manufacturer=str(manufacturer),
            model=str(model),
            acquisition_date=now,
            last_maintenance=now - timedelta(days=min(30, max(1, interval_days // 3))),
            next_maintenance=now + timedelta(days=interval_days),
            operating_hours=float(operating_hours),
            cycles=int(max(0, round(float(operating_hours) * 0.5))),
            location=str(location),
            assigned_unit=str(assigned_unit),
            metadata={"maintenance_interval_days": interval_days},
        )
        self.assets[asset_id] = asset
        self.by_designation[asset.designation] = asset_id
        self.maintenance_records[asset_id] = []
        return asset

    def get_asset(self, asset_id) -> Optional[Asset]:
        return self.assets.get(asset_id)

    def get_by_designation(self, designation) -> Optional[Asset]:
        asset_id = self.by_designation.get(str(designation))
        return self.assets.get(asset_id) if asset_id else None

    def get_assets(
        self,
        asset_type=None,
        status=None,
        condition=None,
        location=None,
        assigned_unit=None,
    ) -> List[Asset]:
        rows = list(self.assets.values())
        if asset_type is not None:
            at = AssetType(asset_type)
            rows = [a for a in rows if a.asset_type == at]
        if status is not None:
            st = AssetStatus(status)
            rows = [a for a in rows if a.status == st]
        if condition is not None:
            cond = AssetCondition(condition)
            rows = [a for a in rows if a.condition == cond]
        if location is not None:
            rows = [a for a in rows if a.location == location]
        if assigned_unit is not None:
            rows = [a for a in rows if a.assigned_unit == assigned_unit]
        return rows

    def update_asset(self, asset_id, **kwargs):
        asset = self.get_asset(asset_id)
        if asset is None:
            raise KeyError(f"Asset not found: {asset_id}")
        for key, value in kwargs.items():
            if not hasattr(asset, key):
                continue
            if key == "asset_type":
                value = AssetType(value)
            elif key == "status":
                value = AssetStatus(value)
            elif key == "condition":
                value = AssetCondition(value)
            setattr(asset, key, value)
        if "designation" in kwargs:
            self.by_designation[str(kwargs["designation"])] = asset_id

    def update_operating_hours(self, asset_id, hours: float):
        asset = self.get_asset(asset_id)
        if asset is None:
            raise KeyError(f"Asset not found: {asset_id}")
        asset.operating_hours = max(0.0, asset.operating_hours + float(hours))

    def update_condition(self, asset_id, condition: AssetCondition):
        asset = self.get_asset(asset_id)
        if asset is None:
            raise KeyError(f"Asset not found: {asset_id}")
        asset.condition = AssetCondition(condition)

    def update_rul(self, asset_id, rul_hours: float, confidence: float):
        asset = self.get_asset(asset_id)
        if asset is None:
            raise KeyError(f"Asset not found: {asset_id}")
        asset.rul_hours = float(rul_hours)
        asset.rul_confidence = max(0.0, min(1.0, float(confidence)))

    def record_maintenance(self, asset_id, record: MaintenanceRecord):
        asset = self.get_asset(asset_id)
        if asset is None:
            raise KeyError(f"Asset not found: {asset_id}")
        self.maintenance_records.setdefault(asset_id, []).append(record)
        asset.maintenance_history.append(record.record_id)
        asset.last_maintenance = record.performed_at
        asset.next_maintenance = record.next_recommended
        asset.condition = record.condition_after

    def get_maintenance_history(self, asset_id) -> List[MaintenanceRecord]:
        return list(self.maintenance_records.get(asset_id, []))

    def get_due_for_maintenance(self) -> List[Asset]:
        return [asset for asset in self.assets.values() if asset.is_due_for_maintenance()]

    def get_critical_assets(self) -> List[Asset]:
        out: List[Asset] = []
        for asset in self.assets.values():
            if asset.condition in {AssetCondition.CRITICAL, AssetCondition.POOR}:
                out.append(asset)
                continue
            if asset.rul_hours is not None and asset.rul_hours < 50:
                out.append(asset)
        return out

    def get_fleet_summary(self) -> dict:
        by_type = Counter(a.asset_type.value for a in self.assets.values())
        by_status = Counter(a.status.value for a in self.assets.values())
        by_condition = Counter(a.condition.value for a in self.assets.values())
        due = self.get_due_for_maintenance()
        critical = self.get_critical_assets()
        return {
            "total": len(self.assets),
            "by_type": dict(by_type),
            "by_status": dict(by_status),
            "by_condition": dict(by_condition),
            "critical_count": len(critical),
            "maintenance_due_count": len(due),
        }

    def create_saudi_fleet_template(self) -> List[Asset]:
        created: List[Asset] = []
        now = datetime.now(timezone.utc)

        def mk(name: str, designation: str, asset_type: AssetType, hrs: float, condition: AssetCondition, unit: str, location: str, serial: str):
            asset = self.register(
                name=name,
                designation=designation,
                asset_type=asset_type,
                serial_number=serial,
                manufacturer="S3M Defense Industries",
                model=name,
                location=location,
                assigned_unit=unit,
                operating_hours=hrs,
            )
            asset.condition = condition
            asset.last_maintenance = now - timedelta(days=max(5, int(hrs // 40)))
            asset.next_maintenance = now + timedelta(days=max(-5, 90 - int(hrs // 60)))
            asset.cycles = int(max(20, hrs * 1.2))
            created.append(asset)

        # F-15SA fighter jets (6)
        for idx, hrs, cond in [
            (201, 3900, AssetCondition.GOOD),
            (202, 4200, AssetCondition.FAIR),
            (203, 4700, AssetCondition.POOR),
            (204, 3300, AssetCondition.GOOD),
            (205, 2800, AssetCondition.EXCELLENT),
            (206, 4500, AssetCondition.FAIR),
        ]:
            mk("F-15SA", f"F-15SA #{idx}", AssetType.FIGHTER_JET, hrs, cond, "RSAF 3rd Wing", "King Abdulaziz Air Base", f"F15-{idx}")

        # AH-64 Apache helicopters (4)
        for idx, hrs, cond in [
            (51, 2600, AssetCondition.GOOD),
            (52, 3100, AssetCondition.FAIR),
            (53, 3400, AssetCondition.POOR),
            (54, 2200, AssetCondition.GOOD),
        ]:
            mk("AH-64 Apache", f"AH-64 #{idx}", AssetType.HELICOPTER, hrs, cond, "Army Aviation Brigade", "Tabuk Air Wing", f"AH64-{idx}")

        # M1A2 Abrams tanks (4)
        for idx, hrs, cond in [
            (107, 5200, AssetCondition.FAIR),
            (108, 6100, AssetCondition.POOR),
            (109, 4800, AssetCondition.GOOD),
            (110, 4300, AssetCondition.GOOD),
        ]:
            mk("M1A2 Abrams", f"M1A2 #{idx}", AssetType.TANK, hrs, cond, "Armored Brigade 1", "Hafr Al-Batin", f"M1A2-{idx}")

        # Patrol boats (3)
        for idx, hrs, cond in [
            (31, 3800, AssetCondition.GOOD),
            (32, 4400, AssetCondition.FAIR),
            (33, 5100, AssetCondition.POOR),
        ]:
            mk("Patrol Boat", f"PB #{idx}", AssetType.PATROL_BOAT, hrs, cond, "Western Fleet", "Jeddah Naval Base", f"PB-{idx}")

        # Radar systems (2)
        for idx, hrs, cond in [
            (71, 2100, AssetCondition.GOOD),
            (72, 2900, AssetCondition.FAIR),
        ]:
            mk("AN/TPS Radar", f"RADAR #{idx}", AssetType.RADAR_SYSTEM, hrs, cond, "Air Defense Command", "Riyadh Sector", f"RAD-{idx}")

        # UAV (1)
        mk("MQ-9 Class UAV", "MQ-9 #01", AssetType.UAV, 1900, AssetCondition.GOOD, "ISR Squadron", "Prince Sultan Air Base", "MQ9-01")

        return created

    def export(self, filepath: str):
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asset.to_dict() for asset in self.assets.values()]
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
