"""Maintenance work-order generation and lifecycle management."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from uuid import uuid4

from services.maintenance.assets.asset_registry import AssetRegistry
from services.maintenance.models import (
    Asset,
    AssetCondition,
    AssetType,
    MaintenanceType,
    WorkOrder,
    WorkOrderPriority,
    WorkOrderStatus,
)


class MaintenanceScheduler:
    """Generate and manage work orders balancing readiness and sustainment."""

    def __init__(self, asset_registry=None, predictive_engine=None, spare_parts=None):
        self.asset_registry = asset_registry or AssetRegistry()
        self.predictive_engine = predictive_engine
        self.spare_parts = spare_parts
        self.work_orders: Dict[str, WorkOrder] = {}

    def _predictive_threshold(self, asset: Asset) -> float:
        if asset.asset_type in {AssetType.AIRCRAFT, AssetType.FIGHTER_JET, AssetType.HELICOPTER, AssetType.TRANSPORT_AIRCRAFT, AssetType.UAV}:
            return 200.0
        if asset.asset_type in {AssetType.GROUND_VEHICLE, AssetType.APC, AssetType.TANK, AssetType.TRUCK}:
            return 500.0
        return 300.0

    def _priority_for_asset(self, asset: Asset) -> WorkOrderPriority:
        if asset.condition == AssetCondition.CRITICAL or (asset.rul_hours is not None and asset.rul_hours < 50):
            return WorkOrderPriority.EMERGENCY
        if asset.rul_hours is not None and asset.rul_hours < 200:
            return WorkOrderPriority.URGENT
        if asset.is_due_for_maintenance():
            return WorkOrderPriority.ROUTINE
        return WorkOrderPriority.SCHEDULED

    def _default_parts(self, asset: Asset) -> List[dict]:
        mapping = {
            AssetType.FIGHTER_JET: [
                {"part_id": "ENG-TB-001", "name": "Engine Turbine Blade", "quantity": 2},
                {"part_id": "OIL-FLT-002", "name": "Oil Filter", "quantity": 4},
            ],
            AssetType.HELICOPTER: [
                {"part_id": "RTR-BLD-015", "name": "Rotor Blade Segment", "quantity": 1},
                {"part_id": "SEAL-KIT-009", "name": "Seal Kit", "quantity": 2},
            ],
            AssetType.TANK: [
                {"part_id": "BRK-PAD-003", "name": "Brake Pad Set", "quantity": 2},
                {"part_id": "TRN-GEAR-016", "name": "Transmission Gear", "quantity": 1},
            ],
            AssetType.PATROL_BOAT: [
                {"part_id": "NVL-FLT-017", "name": "Naval Intake Filter", "quantity": 2},
                {"part_id": "SEAL-KIT-009", "name": "Seal Kit", "quantity": 3},
            ],
            AssetType.RADAR_SYSTEM: [
                {"part_id": "RDR-MOD-004", "name": "Radar Module", "quantity": 1},
                {"part_id": "COM-BRD-005", "name": "Communication Board", "quantity": 1},
            ],
        }
        return mapping.get(asset.asset_type, [{"part_id": "OIL-FLT-002", "name": "Oil Filter", "quantity": 1}])

    def _annotate_stock(self, parts: List[dict]) -> List[dict]:
        if self.spare_parts is None:
            return [{**p, "in_stock": False} for p in parts]

        available = self.spare_parts.get_parts()
        by_number = {part.part_number: part for part in available}
        out = []
        for part in parts:
            inv = by_number.get(part["part_id"])
            in_stock = bool(inv and inv.quantity_on_hand >= int(part.get("quantity", 1)))
            out.append({**part, "in_stock": in_stock})
        return out

    def _llm_schedule_text(self, summary: str) -> str:
        prompt = (
            "Schedule these maintenance work orders for optimal fleet availability. "
            "Consider: part availability, technician capacity, operational tempo. "
            f"Work orders: {summary}."
        )
        try:
            from src.llm_core.inference import S3MInference

            text = S3MInference().generate(prompt, max_tokens=180)
            if isinstance(text, str) and text.strip():
                return text.strip()
        except Exception:
            pass
        return "Prioritize emergency and urgent tasks first, then route routine preventive maintenance to preserve sortie generation."

    def generate_work_orders(self, days_ahead: int = 30) -> List[WorkOrder]:
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(days=int(days_ahead))
        generated: List[WorkOrder] = []

        for asset in self.asset_registry.get_assets():
            reasons: List[tuple[MaintenanceType, str]] = []

            if asset.next_maintenance and asset.next_maintenance <= horizon:
                reasons.append((MaintenanceType.PREVENTIVE, "Calendar interval exceeded"))
            threshold = self._predictive_threshold(asset)
            if asset.rul_hours is not None and asset.rul_hours < threshold:
                reasons.append((MaintenanceType.PREDICTIVE, f"RUL {asset.rul_hours:.1f}h below threshold {threshold:.1f}h"))
            if asset.condition in {AssetCondition.POOR, AssetCondition.CRITICAL}:
                reasons.append((MaintenanceType.CONDITION_BASED, f"Condition {asset.condition.value}"))

            for mtype, reason in reasons:
                priority = self._priority_for_asset(asset)
                parts = self._annotate_stock(self._default_parts(asset))
                wo = WorkOrder(
                    work_order_id=f"wo-{uuid4().hex[:10]}",
                    asset_id=asset.asset_id,
                    title=f"{mtype.value.title()} Maintenance - {asset.designation}",
                    description=f"{reason}. Tactical objective: maintain platform mission readiness.",
                    maintenance_type=mtype,
                    priority=priority,
                    status=WorkOrderStatus.DRAFT,
                    assigned_technician=None,
                    estimated_hours=8.0 if priority in {WorkOrderPriority.ROUTINE, WorkOrderPriority.SCHEDULED} else 12.0,
                    parts_required=parts,
                    created_at=now,
                    scheduled_date=max(now, asset.next_maintenance) if asset.next_maintenance else now,
                    cost_estimate=float(sum(200.0 * int(p.get("quantity", 1)) for p in parts)),
                    notes="",
                )
                wo.llm_recommendation = self._llm_schedule_text(f"{wo.title} priority {wo.priority.value}")
                self.work_orders[wo.work_order_id] = wo
                generated.append(wo)

        order = {
            WorkOrderPriority.EMERGENCY: 0,
            WorkOrderPriority.URGENT: 1,
            WorkOrderPriority.ROUTINE: 2,
            WorkOrderPriority.SCHEDULED: 3,
            WorkOrderPriority.DEFERRED: 4,
        }
        generated.sort(key=lambda wo: (order[wo.priority], wo.scheduled_date or now, wo.created_at))
        return generated

    def approve_work_order(self, work_order_id: str, approved_by: str):
        wo = self.work_orders.get(work_order_id)
        if wo is None:
            raise KeyError(f"Work order not found: {work_order_id}")
        wo.status = WorkOrderStatus.APPROVED
        wo.notes = (wo.notes + "\n" if wo.notes else "") + f"Approved by {approved_by}"

    def start_work_order(self, work_order_id: str, technician: str):
        wo = self.work_orders.get(work_order_id)
        if wo is None:
            raise KeyError(f"Work order not found: {work_order_id}")
        wo.status = WorkOrderStatus.IN_PROGRESS
        wo.assigned_technician = technician
        wo.started_at = datetime.now(timezone.utc)

    def complete_work_order(self, work_order_id: str, notes: str, parts_used: List[dict], cost: float):
        wo = self.work_orders.get(work_order_id)
        if wo is None:
            raise KeyError(f"Work order not found: {work_order_id}")
        wo.status = WorkOrderStatus.COMPLETED
        wo.completed_at = datetime.now(timezone.utc)
        wo.notes = (wo.notes + "\n" if wo.notes else "") + notes
        wo.actual_cost = float(cost)

        if self.spare_parts is not None:
            for part in parts_used:
                part_id = part.get("part_id")
                quantity = int(part.get("quantity", 1))
                if part_id and self.spare_parts.get_part(part_id):
                    self.spare_parts.consume(part_id, quantity)

    def get_work_orders(self, status=None, priority=None, asset_id=None) -> List[WorkOrder]:
        rows = list(self.work_orders.values())
        if status is not None:
            st = WorkOrderStatus(status)
            rows = [wo for wo in rows if wo.status == st]
        if priority is not None:
            pr = WorkOrderPriority(priority)
            rows = [wo for wo in rows if wo.priority == pr]
        if asset_id is not None:
            rows = [wo for wo in rows if wo.asset_id == asset_id]
        rows.sort(key=lambda wo: wo.created_at, reverse=True)
        return rows

    def get_schedule(self, days_ahead: int = 30) -> List[dict]:
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(days=int(days_ahead))
        grouped = defaultdict(list)

        for wo in self.work_orders.values():
            date = wo.scheduled_date or wo.created_at
            if now <= date <= horizon:
                grouped[date.date().isoformat()].append(wo)

        schedule = []
        for date, items in sorted(grouped.items()):
            schedule.append(
                {
                    "date": date,
                    "work_orders": [item.to_dict() for item in items],
                    "assets_affected": len({item.asset_id for item in items}),
                }
            )
        return schedule

    def get_backlog(self) -> List[WorkOrder]:
        return [
            wo
            for wo in self.work_orders.values()
            if wo.status == WorkOrderStatus.APPROVED
        ]

    def get_stats(self) -> dict:
        by_status = Counter(wo.status.value for wo in self.work_orders.values())
        by_priority = Counter(wo.priority.value for wo in self.work_orders.values())
        return {
            "total": len(self.work_orders),
            "by_status": dict(by_status),
            "by_priority": dict(by_priority),
            "backlog": len(self.get_backlog()),
        }
